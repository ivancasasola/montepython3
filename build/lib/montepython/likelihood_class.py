"""
.. module:: likelihood_class
   :synopsis: Definition of the major likelihoods
.. moduleauthor:: Julien Lesgourgues <lesgourg@cern.ch>
.. moduleauthor:: Benjamin Audren <benjamin.audren@epfl.ch>

Contains the definition of the base likelihood class :class:`Likelihood`, with
basic functions, as well as more specific likelihood classes that may be reused
to implement new ones.

"""
import os
import numpy as np
import math
import warnings
import re
import scipy.constants as const

import io_mp


class Likelihood(object):
    """
    General class that all likelihoods will inherit from.

    """

    def __init__(self, path, data, command_line):
        """
        It copies the content of self.path from the initialization routine of
        the :class:`Data <data.Data>` class, and defines a handful of useful
        methods, that every likelihood might need.

        If the nuisance parameters required to compute this likelihood are not
        defined (either fixed or varying), the code will stop.

        Parameters
        ----------
        data : class
            Initialized instance of :class:`Data <data.Data>`
        command_line : NameSpace
            NameSpace containing the command line arguments

        """

        self.name = self.__class__.__name__
        self.folder = os.path.abspath(os.path.join(
            data.path['MontePython'], 'likelihoods', self.name))
        if not data.log_flag:
            path = os.path.join(command_line.folder, 'log.param')

        # Define some default fields
        self.data_directory = ''

        # Store all the default fields stored, for the method read_file.
        self.default_values = ['data_directory']

        # Recover the values potentially read in the input.param file.
        if hasattr(data, self.name):
            exec("attributes = [e for e in dir(data.%s) if e.find('__') == -1]" % self.name)
            for elem in attributes:
                exec("setattr(self, elem, getattr(data.%s, elem))" % self.name)

        # Read values from the data file
        self.read_from_file(path, data, command_line)

        # Default state
        self.need_update = True

        # Check if the nuisance parameters are defined
        error_flag = False
        try:
            for nuisance in self.use_nuisance:
                if nuisance not in data.get_mcmc_parameters(['nuisance']):
                    error_flag = True
                    warnings.warn(
                        nuisance + " must be defined, either fixed or " +
                        "varying, for %s likelihood" % self.name)
            self.nuisance = self.use_nuisance
        except AttributeError:
            self.use_nuisance = []
            self.nuisance = []

        # If at least one is missing, raise an exception.
        if error_flag:
            raise io_mp.LikelihoodError(
                "Check your nuisance parameter list for your set of experiments")

        # Append to the log.param the value used (WARNING: so far no comparison
        # is done to ensure that the experiments share the same parameters)
        if data.log_flag:
            io_mp.log_likelihood_parameters(self, command_line)

    def loglkl(self, cosmo, data):
        """
        Placeholder to remind that this function needs to be defined for a
        new likelihood.

        Raises
        ------
        NotImplementedError

        """
        raise NotImplementedError(
            'Must implement method loglkl() in your likelihood')

    def read_from_file(self, path, data, command_line):
        """
        Extract the information from the log.param concerning this likelihood.

        If the log.param is used, check that at least one item for each
        likelihood is recovered. Otherwise, it means the log.param does not
        contain information on the likelihood. This happens when the first run
        fails early, before calling the likelihoods, and the program did not
        log the information. This check might not be completely secure, but it
        is better than nothing.

        .. warning::

            This checks relies on the fact that a likelihood should always have
            at least **one** line of code written in the likelihood.data file.
            This should be always true, but in case a run fails with the error
            message described below, think about it.

        .. warning::

            As of version 2.0.2, you can specify likelihood options in the
            parameter file. They have complete priority over the ones specified
            in the `likelihood.data` file, and it will be reflected in the
            `log.param` file.

        """

        # Counting how many lines are read.
        counter = 0

        self.path = path
        self.dictionary = {}
        if os.path.isfile(path):
            data_file = open(path, 'r')
            for line in data_file:
                if line.find('#') == -1:
                    if line.find(self.name+'.') != -1:
                        # Recover the name and value from the .data file
                        regexp = re.match(
                            "%s.(.*)\s*=\s*(.*)" % self.name, line)
                        name, value = (
                            elem.strip() for elem in regexp.groups())
                        # If this name was already defined in the parameter
                        # file, be sure to take this value instead. Beware,
                        # there are a few parameters which are always
                        # predefined, such as data_directory, which should be
                        # ignored in this check.
                        is_ignored = False
                        if name not in self.default_values:
                            try:
                                value = getattr(self, name)
                                is_ignored = True
                            except AttributeError:
                                pass
                        if not is_ignored:
                            exec('self.'+name+' = '+value)
                        value = getattr(self, name)
                        counter += 1
                        self.dictionary[name] = value
            data_file.seek(0)
            data_file.close()

        # Checking that at least one line was read, exiting otherwise
        if counter == 0:
            raise io_mp.ConfigurationError(
                "No information on %s likelihood " % self.name +
                "was found in the %s file.\n" % path +
                "This can result from a failed initialization of a previous " +
                "run. To solve this, you can do a \n " +
                "]$ rm -rf %s \n " % command_line.folder +
                "Be sure there is noting in it before doing this !")

    def get_cl(self, cosmo, l_max=-1):
        """
        Return the :math:`C_{\ell}` from the cosmological code in
        :math:`\mu {\\rm K}^2`

        """
        # get C_l^XX from the cosmological code
        cl = cosmo.lensed_cl(l_max)

        # convert dimensionless C_l's to C_l in muK**2
        T = cosmo.T_cmb()
        for key in cl.iterkeys():
            # All quantities need to be multiplied by this factor, except the
            # phi-phi term, that is already dimensionless
            if key not in ['pp', 'ell']:
                cl[key] *= (T*1.e6)**2

        return cl

    def get_unlensed_cl(self, cosmo, l_max=-1):
        """
        Return the :math:`C_{\ell}` from the cosmological code in
        :math:`\mu {\\rm K}^2`

        """
        # get C_l^XX from the cosmological code
        cl = cosmo.raw_cl(l_max)

        # convert dimensionless C_l's to C_l in muK**2
        T = cosmo.T_cmb()
        for key in cl.iterkeys():
            # All quantities need to be multiplied by this factor, except the
            # phi-phi term, that is already dimensionless
            if key not in ['pp', 'ell']:
                cl[key] *= (T*1.e6)**2

        return cl

    def need_cosmo_arguments(self, data, dictionary):
        """
        Ensure that the arguments of dictionary are defined to the correct
        value in the cosmological code

        .. warning::

            So far there is no way to enforce a parameter where `smaller is
            better`. A bigger value will always overried any smaller one
            (`cl_max`, etc...)

        Parameters
        ----------
        data : dict
            Initialized instance of :class:`data`
        dictionary : dict
            Desired precision for some cosmological parameters

        """
        array_flag = False
        for key, value in dictionary.iteritems():
            try:
                data.cosmo_arguments[key]
                try:
                    float(data.cosmo_arguments[key])
                    num_flag = True
                except ValueError:
                    num_flag = False
                except TypeError:
                    num_flag = True
                    array_flag = True

            except KeyError:
                try:
                    float(value)
                    num_flag = True
                    data.cosmo_arguments[key] = 0
                except ValueError:
                    num_flag = False
                    data.cosmo_arguments[key] = ''
                except TypeError:
                    num_flag = True
                    array_flag = True
            if num_flag is False:
                if data.cosmo_arguments[key].find(value) == -1:
                    data.cosmo_arguments[key] += ' '+value+' '
            else:
                if array_flag is False:
                    if float(data.cosmo_arguments[key]) < value:
                        data.cosmo_arguments[key] = value
                else:
                    data.cosmo_arguments[key] = '%.2g' % value[0]
                    for i in range(1, len(value)):
                        data.cosmo_arguments[key] += ',%.2g' % (value[i])

    def read_contamination_spectra(self, data):

        for nuisance in self.use_nuisance:
            # read spectrum contamination (so far, assumes only temperature
            # contamination; will be trivial to generalize to polarization when
            # such templates will become relevant)
            setattr(self, "%s_contamination" % nuisance,
                    np.zeros(self.l_max+1, 'float64'))
            try:
                File = open(os.path.join(
                    self.data_directory, getattr(self, "%s_file" % nuisance)),
                    'r')
                for line in File:
                    l = int(float(line.split()[0]))
                    if ((l >= 2) and (l <= self.l_max)):
                        exec "self.%s_contamination[l]=float(line.split()[1])/(l*(l+1.)/2./math.pi)" % nuisance
            except:
                print 'Warning: you did not pass a file name containing '
                print 'a contamination spectrum regulated by the nuisance '
                print 'parameter '+nuisance

            # read renormalization factor
            # if it is not there, assume it is one, i.e. do not renormalize
            try:
                # do the following operation:
                # self.nuisance_contamination *= float(self.nuisance_scale)
                setattr(self, "%s_contamination" % nuisance,
                        getattr(self, "%s_contamination" % nuisance) *
                        float(getattr(self, "%s_scale" % nuisance)))
            except AttributeError:
                pass

            # read central value of nuisance parameter
            # if it is not there, assume one by default
            try:
                getattr(self, "%s_prior_center" % nuisance)
            except AttributeError:
                setattr(self, "%s_prior_center" % nuisance, 1.)

            # read variance of nuisance parameter
            # if it is not there, assume flat prior (encoded through
            # variance=0)
            try:
                getattr(self, "%s_prior_variance" % nuisance)
            except:
                setattr(self, "%s_prior_variance" % nuisance, 0.)

    def add_contamination_spectra(self, cl, data):

        # Recover the current value of the nuisance parameter.
        for nuisance in self.use_nuisance:
            nuisance_value = float(
                data.mcmc_parameters[nuisance]['current'] *
                data.mcmc_parameters[nuisance]['scale'])

            # add contamination spectra multiplied by nuisance parameters
            for l in range(2, self.l_max):
                exec "cl['tt'][l] += nuisance_value*self.%s_contamination[l]" % nuisance

        return cl

    def add_nuisance_prior(self, lkl, data):

        # Recover the current value of the nuisance parameter.
        for nuisance in self.use_nuisance:
            nuisance_value = float(
                data.mcmc_parameters[nuisance]['current'] *
                data.mcmc_parameters[nuisance]['scale'])

            # add prior on nuisance parameters
            if getattr(self, "%s_prior_variance" % nuisance) > 0:
                # convenience variables
                prior_center = getattr(self, "%s_prior_center" % nuisance)
                prior_variance = getattr(self, "%s_prior_variance" % nuisance)
                lkl += -0.5*((nuisance_value-prior_center)/prior_variance)**2

        return lkl

    def computeLikelihood(self, ctx):
        """
        Interface with CosmoHammer

        Parameters
        ----------
        ctx : Context
                Contains several dictionaries storing data and cosmological
                information

        """
        # Recover both instances from the context
        cosmo = ctx.get("cosmo")
        data = ctx.get("data")

        loglkl = self.loglkl(cosmo, data)

        return loglkl


###################################
#
# END OF GENERIC LIKELIHOOD CLASS
#
###################################



###################################
# PRIOR TYPE LIKELIHOOD
# --> H0,...
###################################
class Likelihood_prior(Likelihood):

    def loglkl(self):
        raise NotImplementedError('Must implement method loglkl() in your likelihood')


###################################
# NEWDAT TYPE LIKELIHOOD
# --> spt,boomerang,etc.
###################################
class Likelihood_newdat(Likelihood):

    def __init__(self, path, data, command_line):

        Likelihood.__init__(self, path, data, command_line)

        self.need_cosmo_arguments(
            data, {'lensing': 'yes', 'output': 'tCl lCl pCl'})

        # open .newdat file
        newdatfile = open(
            os.path.join(self.data_directory, self.file), 'r')

        # find beginning of window functions file names
        window_name = newdatfile.readline().strip('\n').replace(' ', '')

        # initialize list of fist and last band for each type
        band_num = np.zeros(6, 'int')
        band_min = np.zeros(6, 'int')
        band_max = np.zeros(6, 'int')

        # read number of bands for each of the six types TT, EE, BB, EB, TE, TB
        line = newdatfile.readline()
        for i in range(6):
            band_num[i] = int(line.split()[i])

        # read string equal to 'BAND_SELECTION' or not
        line = str(newdatfile.readline()).strip('\n').replace(' ', '')

        # if yes, read 6 lines containing 'min, max'
        if (line == 'BAND_SELECTION'):
            for i in range(6):
                line = newdatfile.readline()
                band_min[i] = int(line.split()[0])
                band_max[i] = int(line.split()[1])

        # if no, set min to 1 and max to band_num (=use all bands)
        else:
            band_min = [1 for i in range(6)]
            band_max = band_num

        # read line defining calibration uncertainty
        # contains: flag (=0 or 1), calib, calib_uncertainty
        line = newdatfile.readline()
        calib = float(line.split()[1])
        if (int(line.split()[0]) == 0):
            self.calib_uncertainty = 0
        else:
            self.calib_uncertainty = float(line.split()[2])

        # read line defining beam uncertainty
        # contains: flag (=0, 1 or 2), beam_width, beam_sigma
        line = newdatfile.readline()
        beam_type = int(line.split()[0])
        if (beam_type > 0):
            self.has_beam_uncertainty = True
        else:
            self.has_beam_uncertainty = False
        beam_width = float(line.split()[1])
        beam_sigma = float(line.split()[2])

        # read flag (= 0, 1 or 2) for lognormal distributions and xfactors
        line = newdatfile.readline()
        likelihood_type = int(line.split()[0])
        if (likelihood_type > 0):
            self.has_xfactors = True
        else:
            self.has_xfactors = False

        # declare array of quantitites describing each point of measurement
        # size yet unknown, it will be found later and stored as
        # self.num_points
        self.obs = np.array([], 'float64')
        self.var = np.array([], 'float64')
        self.beam_error = np.array([], 'float64')
        self.has_xfactor = np.array([], 'bool')
        self.xfactor = np.array([], 'float64')

        # temporary array to know which bands are actually used
        used_index = np.array([], 'int')

        index = -1

        # scan the lines describing each point of measurement
        for cltype in range(6):
            if (int(band_num[cltype]) != 0):
                # read name (but do not use it)
                newdatfile.readline()
                for band in range(int(band_num[cltype])):
                    # read one line corresponding to one measurement
                    line = newdatfile.readline()
                    index += 1

                    # if we wish to actually use this measurement
                    if ((band >= band_min[cltype]-1) and
                            (band <= band_max[cltype]-1)):

                        used_index = np.append(used_index, index)

                        self.obs = np.append(
                            self.obs, float(line.split()[1])*calib**2)

                        self.var = np.append(
                            self.var,
                            (0.5*(float(line.split()[2]) +
                                  float(line.split()[3]))*calib**2)**2)

                        self.xfactor = np.append(
                            self.xfactor, float(line.split()[4])*calib**2)

                        if ((likelihood_type == 0) or
                                ((likelihood_type == 2) and
                                (int(line.split()[7]) == 0))):
                            self.has_xfactor = np.append(
                                self.has_xfactor, [False])
                        if ((likelihood_type == 1) or
                                ((likelihood_type == 2) and
                                (int(line.split()[7]) == 1))):
                            self.has_xfactor = np.append(
                                self.has_xfactor, [True])

                        if (beam_type == 0):
                            self.beam_error = np.append(self.beam_error, 0.)
                        if (beam_type == 1):
                            l_mid = float(line.split()[5]) +\
                                0.5*(float(line.split()[5]) +
                                     float(line.split()[6]))
                            self.beam_error = np.append(
                                self.beam_error,
                                abs(math.exp(
                                    -l_mid*(l_mid+1)*1.526e-8*2.*beam_sigma *
                                    beam_width)-1.))
                        if (beam_type == 2):
                            if (likelihood_type == 2):
                                self.beam_error = np.append(
                                    self.beam_error, float(line.split()[8]))
                            else:
                                self.beam_error = np.append(
                                    self.beam_error, float(line.split()[7]))

                # now, skip and unused part of the file (with sub-correlation
                # matrices)
                for band in range(int(band_num[cltype])):
                    newdatfile.readline()

        # number of points that we will actually use
        self.num_points = np.shape(self.obs)[0]

        # total number of points, including unused ones
        full_num_points = index+1

        # read full correlation matrix
        full_covmat = np.zeros((full_num_points, full_num_points), 'float64')
        for point in range(full_num_points):
            full_covmat[point] = newdatfile.readline().split()

        # extract smaller correlation matrix for points actually used
        covmat = np.zeros((self.num_points, self.num_points), 'float64')
        for point in range(self.num_points):
            covmat[point] = full_covmat[used_index[point], used_index]

        # recalibrate this correlation matrix
        covmat *= calib**4

        # redefine the correlation matrix, the observed points and their
        # variance in case of lognormal likelihood
        if (self.has_xfactors):

            for i in range(self.num_points):

                for j in range(self.num_points):
                    if (self.has_xfactor[i]):
                        covmat[i, j] /= (self.obs[i]+self.xfactor[i])
                    if (self.has_xfactor[j]):
                        covmat[i, j] /= (self.obs[j]+self.xfactor[j])

            for i in range(self.num_points):
                if (self.has_xfactor[i]):
                    self.var[i] /= (self.obs[i]+self.xfactor[i])**2
                    self.obs[i] = math.log(self.obs[i]+self.xfactor[i])

        # invert correlation matrix
        self.inv_covmat = np.linalg.inv(covmat)

        # read window function files a first time, only for finding the
        # smallest and largest l's for each point
        self.win_min = np.zeros(self.num_points, 'int')
        self.win_max = np.zeros(self.num_points, 'int')
        for point in range(self.num_points):
            for line in open(os.path.join(
                    self.data_directory, 'windows', window_name) +
                    str(used_index[point]+1), 'r'):
                if any([float(line.split()[i]) != 0.
                        for i in range(1, len(line.split()))]):
                    if (self.win_min[point] == 0):
                        self.win_min[point] = int(line.split()[0])
                    self.win_max[point] = int(line.split()[0])

        # infer from format of window function files whether we will use
        # polarisation spectra or not
        num_col = len(line.split())
        if (num_col == 2):
            self.has_pol = False
        else:
            if (num_col == 5):
                self.has_pol = True
            else:
                raise io_mp.LikelihoodError(
                    "In likelihood %s. " % self.name +
                    "Window function files are understood if they contain " +
                    "2 columns (l TT), or 5 columns (l TT TE EE BB)." +
                    "In this case the number of columns is %d" % num_col)

        # define array of window functions
        self.window = np.zeros(
            (self.num_points, max(self.win_max)+1, num_col-1), 'float64')

        # go again through window function file, this time reading window
        # functions; that are distributed as: l TT (TE EE BB) where the last
        # columns contaim W_l/l, not W_l we mutiply by l in order to store the
        # actual W_l
        for point in range(self.num_points):
            for line in open(os.path.join(
                    self.data_directory, 'windows', window_name) +
                    str(used_index[point]+1), 'r'):
                l = int(line.split()[0])
                if (((self.has_pol is False) and (len(line.split()) != 2))
                        or ((self.has_pol is True) and
                            (len(line.split()) != 5))):
                    raise io_mp.LikelihoodError(
                        "In likelihood %s. " % self.name +
                        "for a given experiment, all window functions should" +
                        " have the same number of columns, 2 or 5. " +
                        "This is not the case here.")
                if ((l >= self.win_min[point]) and (l <= self.win_max[point])):
                    self.window[point, l, :] = [
                        float(line.split()[i])
                        for i in range(1, len(line.split()))]
                    self.window[point, l, :] *= l

        # eventually, initialise quantitites used in the marginalization over
        # nuisance parameters
        if ((self.has_xfactors) and
                ((self.calib_uncertainty > 1.e-4) or
                 (self.has_beam_uncertainty))):
            self.halfsteps = 5
            self.margeweights = np.zeros(2*self.halfsteps+1, 'float64')
            for i in range(-self.halfsteps, self.halfsteps+1):
                self.margeweights[i+self.halfsteps] = np.exp(
                    -(float(i)*3./float(self.halfsteps))**2/2)
            self.margenorm = sum(self.margeweights)

        # store maximum value of l needed by window functions
        self.l_max = max(self.win_max)

        # impose that the cosmological code computes Cl's up to maximum l
        # needed by the window function
        self.need_cosmo_arguments(data, {'l_max_scalars': self.l_max})

        # deal with nuisance parameters
        try:
            self.use_nuisance
            self.nuisance = self.use_nuisance
        except:
            self.use_nuisance = []
            self.nuisance = []
        self.read_contamination_spectra(data)

        # end of initialisation

    def loglkl(self, cosmo, data):
        # get Cl's from the cosmological code
        cl = self.get_cl(cosmo)

        # add contamination spectra multiplied by nuisance parameters
        cl = self.add_contamination_spectra(cl, data)

        # get likelihood
        lkl = self.compute_lkl(cl, cosmo, data)

        # add prior on nuisance parameters
        lkl = self.add_nuisance_prior(lkl, data)

        return lkl

    def compute_lkl(self, cl, cosmo, data):
        # checks that Cl's have been computed up to high enough l given window
        # function range. Normally this has been imposed before, so this test
        # could even be supressed.
        if (np.shape(cl['tt'])[0]-1 < self.l_max):
            raise io_mp.LikelihoodError(
                "%s computed Cls till l=" % data.cosmological_module_name +
                "%d " % (np.shape(cl['tt'])[0]-1) +
                "while window functions need %d." % self.l_max)

        # compute theoretical bandpowers, store them in theo[points]
        theo = np.zeros(self.num_points, 'float64')

        for point in range(self.num_points):

            # find bandpowers B_l by convolving C_l's with [(l+1/2)/2pi W_l]
            for l in range(self.win_min[point], self.win_max[point]):

                theo[point] += cl['tt'][l]*self.window[point, l, 0] *\
                    (l+0.5)/2./math.pi

                if (self.has_pol):
                    theo[point] += (
                        cl['te'][l]*self.window[point, l, 1] +
                        cl['ee'][l]*self.window[point, l, 2] +
                        cl['bb'][l]*self.window[point, l, 3]) *\
                        (l+0.5)/2./math.pi

        # allocate array for differencve between observed and theoretical
        # bandpowers
        difference = np.zeros(self.num_points, 'float64')

        # depending on the presence of lognormal likelihood, calibration
        # uncertainty and beam uncertainity, use several methods for
        # marginalising over nuisance parameters:

        # first method: numerical integration over calibration uncertainty:
        if (self.has_xfactors and
                ((self.calib_uncertainty > 1.e-4) or
                 self.has_beam_uncertainty)):

            chisq_tmp = np.zeros(2*self.halfsteps+1, 'float64')
            chisqcalib = np.zeros(2*self.halfsteps+1, 'float64')
            beam_error = np.zeros(self.num_points, 'float64')

            # loop over various beam errors
            for ibeam in range(2*self.halfsteps+1):

                # beam error
                for point in range(self.num_points):
                    if (self.has_beam_uncertainty):
                        beam_error[point] = 1.+self.beam_error[point] *\
                            (ibeam-self.halfsteps)*3/float(self.halfsteps)
                    else:
                        beam_error[point] = 1.

                # loop over various calibraion errors
                for icalib in range(2*self.halfsteps+1):

                    # calibration error
                    calib_error = 1+self.calib_uncertainty*(
                        icalib-self.halfsteps)*3/float(self.halfsteps)

                    # compute difference between observed and theoretical
                    # points, after correcting the later for errors
                    for point in range(self.num_points):

                        # for lognormal likelihood, use log(B_l+X_l)
                        if (self.has_xfactor[point]):
                            difference[point] = self.obs[point] -\
                                math.log(
                                    theo[point]*beam_error[point] *
                                    calib_error+self.xfactor[point])
                        # otherwise use B_l
                        else:
                            difference[point] = self.obs[point] -\
                                theo[point]*beam_error[point]*calib_error

                    # find chisq with those corrections
                    # chisq_tmp[icalib] = np.dot(np.transpose(difference),
                    # np.dot(self.inv_covmat, difference))
                    chisq_tmp[icalib] = np.dot(
                        difference, np.dot(self.inv_covmat, difference))

                minchisq = min(chisq_tmp)

            # find chisq marginalized over calibration uncertainty (if any)
                tot = 0
                for icalib in range(2*self.halfsteps+1):
                    tot += self.margeweights[icalib]*math.exp(
                        max(-30., -(chisq_tmp[icalib]-minchisq)/2.))

                chisqcalib[ibeam] = -2*math.log(tot/self.margenorm)+minchisq

            # find chisq marginalized over beam uncertainty (if any)
            if (self.has_beam_uncertainty):

                minchisq = min(chisqcalib)

                tot = 0
                for ibeam in range(2*self.halfsteps+1):
                    tot += self.margeweights[ibeam]*math.exp(
                        max(-30., -(chisqcalib[ibeam]-minchisq)/2.))

                chisq = -2*math.log(tot/self.margenorm)+minchisq

            else:
                chisq = chisqcalib[0]

        # second method: marginalize over nuisance parameters (if any)
        # analytically
        else:

            # for lognormal likelihood, theo[point] should contain log(B_l+X_l)
            if (self.has_xfactors):
                for point in range(self.num_points):
                    if (self.has_xfactor[point]):
                        theo[point] = math.log(theo[point]+self.xfactor[point])

            # find vector of difference between observed and theoretical
            # bandpowers
            difference = self.obs-theo

            # find chisq
            chisq = np.dot(
                np.transpose(difference), np.dot(self.inv_covmat, difference))

            # correct eventually for effect of analytic marginalization over
            # nuisance parameters
            if ((self.calib_uncertainty > 1.e-4) or self.has_beam_uncertainty):

                denom = 1.
                tmpi = np.dot(self.inv_covmat, theo)
                chi2op = np.dot(np.transpose(difference), tmp)
                chi2pp = np.dot(np.transpose(theo), tmp)

                # TODO beam is not defined here !
                if (self.has_beam_uncertainty):
                    for points in range(self.num_points):
                        beam[point] = self.beam_error[point]*theo[point]
                    tmp = np.dot(self.inv_covmat, beam)
                    chi2dd = np.dot(np.transpose(beam), tmp)
                    chi2pd = np.dot(np.transpose(theo), tmp)
                    chi2od = np.dot(np.transpose(difference), tmp)

                if (self.calib_uncertainty > 1.e-4):
                    wpp = 1/(chi2pp+1/self.calib_uncertainty**2)
                    chisq = chisq-wpp*chi2op**2
                    denom = denom/wpp*self.calib_uncertainty**2
                else:
                    wpp = 0

                if (self.has_beam_uncertainty):
                    wdd = 1/(chi2dd-wpp*chi2pd**2+1)
                    chisq = chisq-wdd*(chi2od-wpp*chi2op*chi2pd)**2
                    denom = denom/wdd

                chisq += math.log(denom)

        # finally, return ln(L)=-chi2/2

        self.lkl = -0.5 * chisq
        return self.lkl


###################################
# CLIK TYPE LIKELIHOOD
# --> clik_fake_planck,clik_wmap,etc.
###################################
class Likelihood_clik(Likelihood):

    def __init__(self, path, data, command_line):

        Likelihood.__init__(self, path, data, command_line)
        self.need_cosmo_arguments(
            data, {'lensing': 'yes', 'output': 'tCl lCl pCl'})

        try:
            import clik
        except ImportError:
            raise io_mp.MissingLibraryError(
                "You must first activate the binaries from the Clik " +
                "distribution. Please run : \n " +
                "]$ source /path/to/clik/bin/clik_profile.sh \n " +
                "and try again.")
        # for lensing, some routines change. Intializing a flag for easier
        # testing of this condition
        #if self.name == 'Planck_lensing':
        if 'lensing' in self.name and 'Planck' in self.name:
            self.lensing = True
        else:
            self.lensing = False

        try:
            if self.lensing:
                self.clik = clik.clik_lensing(self.path_clik)
                try:
                    self.l_max = max(self.clik.get_lmax())
                # following 2 lines for compatibility with lensing likelihoods of 2013 and before
                # (then, clik.get_lmax() just returns an integer for lensing likelihoods;
                # this behavior was for clik versions < 10)
                except:
                    self.l_max = self.clik.get_lmax()
            else:
                self.clik = clik.clik(self.path_clik)
                self.l_max = max(self.clik.get_lmax())
        except clik.lkl.CError:
            raise io_mp.LikelihoodError(
                "The path to the .clik file for the likelihood "
                "%s was not found where indicated:\n%s\n"
                % (self.name,self.path_clik) +
                " Note that the default path to search for it is"
                " one directory above the path['clik'] field. You"
                " can change this behaviour in all the "
                "Planck_something.data, to reflect your local configuration, "
                "or alternatively, move your .clik files to this place.")
        except KeyError:
            raise io_mp.LikelihoodError(
                "In the %s.data file, the field 'clik' of the " % self.name +
                "path dictionary is expected to be defined. Please make sure"
                " it is the case in you configuration file")

        self.need_cosmo_arguments(
            data, {'l_max_scalars': self.l_max})

        self.nuisance = list(self.clik.extra_parameter_names)

        # line added to deal with a bug in planck likelihood release: A_planck called A_Planck in plik_lite
        if (self.name == 'Planck_highl_lite'):
            for i in range(len(self.nuisance)):
                if (self.nuisance[i] == 'A_Planck'):
                    self.nuisance[i] = 'A_planck'
            print "In %s, MontePython corrected nuisance parameter name A_Planck to A_planck" % self.name

        # testing if the nuisance parameters are defined. If there is at least
        # one non defined, raise an exception.
        exit_flag = False
        nuisance_parameter_names = data.get_mcmc_parameters(['nuisance'])
        for nuisance in self.nuisance:
            if nuisance not in nuisance_parameter_names:
                exit_flag = True
                print '%20s\tmust be a fixed or varying nuisance parameter' % nuisance

        if exit_flag:
            raise io_mp.LikelihoodError(
                "The likelihood %s " % self.name +
                "expected some nuisance parameters that were not provided")

        # deal with nuisance parameters
        try:
            self.use_nuisance
        except:
            self.use_nuisance = []

        # Add in use_nuisance all the parameters that have non-flat prior
        for nuisance in self.nuisance:
            if hasattr(self, '%s_prior_center' % nuisance):
                self.use_nuisance.append(nuisance)

    def loglkl(self, cosmo, data):

        nuisance_parameter_names = data.get_mcmc_parameters(['nuisance'])

        # get Cl's from the cosmological code
        cl = self.get_cl(cosmo)

        # testing for lensing
        if self.lensing:
            try:
                length = len(self.clik.get_lmax())
                tot = np.zeros(
                    np.sum(self.clik.get_lmax()) + length +
                    len(self.clik.get_extra_parameter_names()))
            # following 3 lines for compatibility with lensing likelihoods of 2013 and before
            # (then, clik.get_lmax() just returns an integer for lensing likelihoods,
            # and the length is always 2 for cl['pp'], cl['tt'])
            except:
                length = 2
                tot = np.zeros(2*self.l_max+length + len(self.clik.get_extra_parameter_names()))
        else:
            length = len(self.clik.get_has_cl())
            tot = np.zeros(
                np.sum(self.clik.get_lmax()) + length +
                len(self.clik.get_extra_parameter_names()))

        # fill with Cl's
        index = 0
        if not self.lensing:
            for i in range(length):
                if (self.clik.get_lmax()[i] > -1):
                    for j in range(self.clik.get_lmax()[i]+1):
                        if (i == 0):
                            tot[index+j] = cl['tt'][j]
                        if (i == 1):
                            tot[index+j] = cl['ee'][j]
                        if (i == 2):
                            tot[index+j] = cl['bb'][j]
                        if (i == 3):
                            tot[index+j] = cl['te'][j]
                        if (i == 4):
                            tot[index+j] = 0 #cl['tb'][j] class does not compute tb
                        if (i == 5):
                            tot[index+j] = 0 #cl['eb'][j] class does not compute eb

                    index += self.clik.get_lmax()[i]+1

        else:
            try:
                for i in range(length):
                    if (self.clik.get_lmax()[i] > -1):
                        for j in range(self.clik.get_lmax()[i]+1):
                            if (i == 0):
                                tot[index+j] = cl['pp'][j]
                            if (i == 1):
                                tot[index+j] = cl['tt'][j]
                            if (i == 2):
                                tot[index+j] = cl['ee'][j]
                            if (i == 3):
                                tot[index+j] = cl['bb'][j]
                            if (i == 4):
                                tot[index+j] = cl['te'][j]
                            if (i == 5):
                                tot[index+j] = 0 #cl['tb'][j] class does not compute tb
                            if (i == 6):
                                tot[index+j] = 0 #cl['eb'][j] class does not compute eb

                        index += self.clik.get_lmax()[i]+1

            # following 8 lines for compatibility with lensing likelihoods of 2013 and before
            # (then, clik.get_lmax() just returns an integer for lensing likelihoods,
            # and the length is always 2 for cl['pp'], cl['tt'])
            except:
                for i in range(length):
                    for j in range(self.l_max):
                        if (i == 0):
                            tot[index+j] = cl['pp'][j]
                        if (i == 1):
                            tot[index+j] = cl['tt'][j]
                    index += self.l_max+1

        # fill with nuisance parameters
        for nuisance in self.clik.get_extra_parameter_names():

            # line added to deal with a bug in planck likelihood release: A_planck called A_Planck in plik_lite
            if (self.name == 'Planck_highl_lite'):
                if nuisance == 'A_Planck':
                    nuisance = 'A_planck'

            if nuisance in nuisance_parameter_names:
                nuisance_value = data.mcmc_parameters[nuisance]['current'] *\
                    data.mcmc_parameters[nuisance]['scale']
            else:
                raise io_mp.LikelihoodError(
                    "the likelihood needs a parameter %s. " % nuisance +
                    "You must pass it through the input file " +
                    "(as a free nuisance parameter or a fixed parameter)")
            #print "found one nuisance with name",nuisance
            tot[index] = nuisance_value
            index += 1

        # compute likelihood
        #print "lkl:",self.clik(tot)
        lkl = self.clik(tot)[0]

        # add prior on nuisance parameters
        lkl = self.add_nuisance_prior(lkl, data)

        return lkl


###################################
# MOCK CMB TYPE LIKELIHOOD
# --> mock planck, cmbpol, etc.
###################################
class Likelihood_mock_cmb(Likelihood):

    def __init__(self, path, data, command_line):

        Likelihood.__init__(self, path, data, command_line)

        self.need_cosmo_arguments(
            data, {'lensing': 'yes', 'output': 'tCl lCl pCl'})

        ################
        # Noise spectrum
        ################

        # convert arcmin to radians
        self.theta_fwhm *= np.array([math.pi/60/180])
        self.sigma_T *= np.array([math.pi/60/180])
        self.sigma_P *= np.array([math.pi/60/180])

        # compute noise in muK**2
        self.noise_T = np.zeros(self.l_max+1, 'float64')
        self.noise_P = np.zeros(self.l_max+1, 'float64')

        for l in range(self.l_min, self.l_max+1):
            self.noise_T[l] = 0
            self.noise_P[l] = 0
            for channel in range(self.num_channels):
                self.noise_T[l] += self.sigma_T[channel]**-2 *\
                    math.exp(
                        -l*(l+1)*self.theta_fwhm[channel]**2/8/math.log(2))
                self.noise_P[l] += self.sigma_P[channel]**-2 *\
                    math.exp(
                        -l*(l+1)*self.theta_fwhm[channel]**2/8/math.log(2))
            self.noise_T[l] = 1/self.noise_T[l]
            self.noise_P[l] = 1/self.noise_P[l]

        # impose that the cosmological code computes Cl's up to maximum l
        # needed by the window function
        self.need_cosmo_arguments(data, {'l_max_scalars': self.l_max})

        ###########################################################################
        # implementation of default settings for flags describing the likelihood: #
        ###########################################################################

        # - ignore B modes by default:
        try:
            self.Bmodes
        except:
            self.Bmodes = False
        # - do not use delensing by default:
        try:
            self.delensing
        except:
            self.delensing = False
        # - do not include lensing extraction by default:
        try:
            self.LensingExtraction
        except:
            self.LensingExtraction = False
        # - neglect TD correlation by default:
        try:
            self.neglect_TD
        except:
            self.neglect_TD = True
        # - use lthe lensed TT, TE, EE by default:
        try:
            self.unlensed_clTTTEEE
        except:
            self.unlensed_clTTTEEE = False

        ##############################################
        # Delensing noise: implemented by  S. Clesse #
        ##############################################

        if self.delensing:

            try:
                self.delensing_file
            except:
                raise io_mp.LikelihoodError("For delensing, you must provide delensing_file")

            self.noise_delensing = np.zeros(self.l_max+1)
            if os.path.exists(os.path.join(self.data_directory, self.delensing_file)):
                delensing_file = open(os.path.join(
                    self.data_directory, self.delensing_file), 'r')
                line = delensing_file.readline()
                while line.find('#') != -1:
                    line = delensing_file.readline()

                for l in range(self.l_min, self.l_max+1):
                    ll = int(float(line.split()[0]))
                    if l != ll:
                        raise io_mp.LikelihoodError("Mismatch between required values of l in the code and in the delensing file")
                    self.noise_delensing[ll] = float(line.split()[2])/(ll*(ll+1)/2./math.pi)
                    # change 3 to 4 in the above line for CMBxCIB delensing
                    line = delensing_file.readline()

            else:
                raise io_mp.LikelihoodError("Could not find file ",self.delensing_file)

        ###############################################################
        # Read data for TT, EE, TE, [eventually BB or phi-phi, phi-T] #
        ###############################################################

        # default:
        numCls = 3

        # deal with BB:
        if self.Bmodes:
            self.index_B = numCls
            numCls += 1

        # deal with pp, pT (p = CMB lensing potential):
        if self.LensingExtraction:
            self.index_pp = numCls
            numCls += 1
            self.index_tp = numCls
            numCls += 1

            # provide a file containing NlDD (noise for the extracted
            # deflection field spectrum) This option is temporary
            # because at some point this module will compute NlDD
            # itself, when logging the fiducial model spectrum.
            try:
                self.temporary_Nldd_file
            except:
                raise io_mp.LikelihoodError("For lensing extraction, you must provide a temporary_Nldd_file")

            # read the NlDD file
            self.Nldd = np.zeros(self.l_max+1, 'float64')

            if os.path.exists(os.path.join(self.data_directory, self.temporary_Nldd_file)):
                fid_file = open(os.path.join(self.data_directory, self.temporary_Nldd_file), 'r')
                line = fid_file.readline()
                while line.find('#') != -1:
                    line = fid_file.readline()
                while (line.find('\n') != -1 and len(line) == 1):
                    line = fid_file.readline()
                for l in range(self.l_min, self.l_max+1):
                    ll = int(float(line.split()[0]))
                    if l != ll:
                        raise io_mp.LikelihoodError("Mismatch between required values of l in the code and in the delensing file")
                    # this lines assumes that Nldd is stored in the
                    # 4th column (can be customised)
                    self.Nldd[ll] = float(line.split()[3])/(l*(l+1.)/2./math.pi)
                    line = fid_file.readline()
            else:
                raise io_mp.LikelihoodError("Could not find file ",self.temporary_Nldd_file)

        # deal with fiducial model:
        # If the file exists, initialize the fiducial values
        self.Cl_fid = np.zeros((numCls, self.l_max+1), 'float64')
        self.fid_values_exist = False
        if os.path.exists(os.path.join(
                self.data_directory, self.fiducial_file)):
            self.fid_values_exist = True
            fid_file = open(os.path.join(
                self.data_directory, self.fiducial_file), 'r')
            line = fid_file.readline()
            while line.find('#') != -1:
                line = fid_file.readline()
            while (line.find('\n') != -1 and len(line) == 1):
                line = fid_file.readline()
            for l in range(self.l_min, self.l_max+1):
                ll = int(line.split()[0])
                self.Cl_fid[0, ll] = float(line.split()[1])
                self.Cl_fid[1, ll] = float(line.split()[2])
                self.Cl_fid[2, ll] = float(line.split()[3])
                # read BB:
                if self.Bmodes:
                    try:
                        self.Cl_fid[self.index_B, ll] = float(line.split()[self.index_B+1])
                    except:
                        raise io_mp.LikelihoodError(
                            "The fiducial model does not have enough columns.")
                # read DD, TD (D = deflection field):
                if self.LensingExtraction:
                    try:
                        self.Cl_fid[self.index_pp, ll] = float(line.split()[self.index_pp+1])
                        self.Cl_fid[self.index_tp, ll] = float(line.split()[self.index_tp+1])
                    except:
                        raise io_mp.LikelihoodError(
                            "The fiducial model does not have enough columns.")

                line = fid_file.readline()

        # Else the file will be created in the loglkl() function.

        # Explicitly display the flags to be sure that likelihood does what you expect:
        print "Initialised likelihood_mock_cmb with following options:"
        if self.unlensed_clTTTEEE:
            print "  unlensed_clTTTEEE is True"
        else:
            print "  unlensed_clTTTEEE is False"
        if self.Bmodes:
            print "  Bmodes is True"
        else:
            print "  Bmodes is False"
        if self.delensing:
            print "  delensing is True"
        else:
            print "  delensing is False"
        if self.LensingExtraction:
            print "  LensingExtraction is True"
        else:
            print "  LensingExtraction is False"
        if self.neglect_TD:
            print "  neglect_TD is True"
        else:
            print "  neglect_TD is False"
        print ""

        # end of initialisation
        return

    def loglkl(self, cosmo, data):

        # get Cl's from the cosmological code (returned in muK**2 units)

        # if we want unlensed Cl's
        if self.unlensed_clTTTEEE:
            cl = self.get_unlensed_cl(cosmo)
            # exception: for non-delensed B modes we need the lensed BB spectrum
            # (this case is usually not useful/relevant)
            if self.Bmodes and (not self.delensing):
                    cl_lensed = self.get_cl(cosmo)
                    for l in range(self.lmax+1):
                        cl[l]['bb']=cl_lensed[l]['bb']

        # if we want lensed Cl's
        else:
            cl = self.get_cl(cosmo)
            # exception: for delensed B modes we need the unlensed spectrum
            if self.Bmodes and self.delensing:
                cl_unlensed = self.get_unlensed_cl(cosmo)
                for l in range(self.lmax+1):
                        cl[l]['bb']=cl_unlensed[l]['bb']

        # get likelihood
        lkl = self.compute_lkl(cl, cosmo, data)

        return lkl

    def compute_lkl(self, cl, cosmo, data):

        # Write fiducial model spectra if needed (return an imaginary number in
        # that case)
        if self.fid_values_exist is False:
            # Store the values now.
            fid_file = open(os.path.join(
                self.data_directory, self.fiducial_file), 'w')
            fid_file.write('# Fiducial parameters')
            for key, value in data.mcmc_parameters.iteritems():
                fid_file.write(', %s = %.5g' % (
                    key, value['current']*value['scale']))
            fid_file.write('\n')
            for l in range(self.l_min, self.l_max+1):
                fid_file.write("%5d  " % l)
                fid_file.write("%.8g  " % (cl['tt'][l]+self.noise_T[l]))
                fid_file.write("%.8g  " % (cl['ee'][l]+self.noise_P[l]))
                fid_file.write("%.8g  " % cl['te'][l])
                if self.Bmodes:
                    # next three lines added by S. Clesse for delensing
                    if self.delensing:
                        fid_file.write("%.8g  " % (cl['bb'][l]+self.noise_P[l]+self.noise_delensing[l]))
                    else:
                        fid_file.write("%.8g  " % (cl['bb'][l]+self.noise_P[l]))
                if self.LensingExtraction:
                    # we want to store clDD = l(l+1) clpp
                    # and ClTD = sqrt(l(l+1)) Cltp
                    fid_file.write("%.8g  " % (l*(l+1.)*cl['pp'][l] + self.Nldd[l]))
                    fid_file.write("%.8g  " % (math.sqrt(l*(l+1.))*cl['tp'][l]))
                fid_file.write("\n")
            print '\n'
            warnings.warn(
                "Writing fiducial model in %s, for %s likelihood\n" % (
                    self.data_directory+'/'+self.fiducial_file, self.name))
            return 1j

        # compute likelihood

        chi2 = 0

        # cound number of modes.
        # number of modes is different form number of spectra
        # modes = T,E,[B],[D=deflection]
        # spectra = TT,EE,TE,[BB],[DD,TD]
        # default:
        num_modes=2
        # add B mode:
        if self.Bmodes:
            num_modes += 1
        # add D mode:
        if self.LensingExtraction:
            num_modes += 1

        Cov_obs = np.zeros((num_modes, num_modes), 'float64')
        Cov_the = np.zeros((num_modes, num_modes), 'float64')
        Cov_mix = np.zeros((num_modes, num_modes), 'float64')

        for l in range(self.l_min, self.l_max+1):

            if self.Bmodes and self.LensingExtraction:
                raise io_mp.LikelihoodError("We have implemented a version of the liklihood with B modes, a version with lensing extraction, but not yet a version with both at the same time. You can implement it.")

            # case with B modes:
            elif self.Bmodes:
                Cov_obs = np.array([
                    [self.Cl_fid[0, l], self.Cl_fid[2, l], 0],
                    [self.Cl_fid[2, l], self.Cl_fid[1, l], 0],
                    [0, 0, self.Cl_fid[3, l]]])
                # next 5 lines added by S. Clesse for delensing
                if self.delensing:
                    Cov_the = np.array([
                        [cl['tt'][l]+self.noise_T[l], cl['te'][l], 0],
                        [cl['te'][l], cl['ee'][l]+self.noise_P[l], 0],
                        [0, 0, cl['bb'][l]+self.noise_P[l]+self.noise_delensing[l]]])
                else:
                    Cov_the = np.array([
                        [cl['tt'][l]+self.noise_T[l], cl['te'][l], 0],
                        [cl['te'][l], cl['ee'][l]+self.noise_P[l], 0],
                        [0, 0, cl['bb'][l]+self.noise_P[l]]])

            # case with lensing
            # note that the likelihood is base on ClDD (deflection spectrum)
            # rather than Clpp (lensing potential spectrum)
            # But the Bolztmann code input is Clpp
            # So we make the conversion using ClDD = l*(l+1.)*Clpp
            # So we make the conversion using ClTD = sqrt(l*(l+1.))*Cltp
            elif self.LensingExtraction:

                cldd_fid = self.Cl_fid[self.index_pp, l]
                cldd = l*(l+1.)*cl['pp'][l]
                if self.neglect_TD:
                    cltd_fid = 0.
                    cltd = 0.
                else:
                    cltd_fid = self.Cl_fid[self.index_tp, l]
                    cltd = math.sqrt(l*(l+1.))*cl['tp'][l]

                Cov_obs = np.array([
                    [self.Cl_fid[0, l], self.Cl_fid[2, l], 0.*self.Cl_fid[self.index_tp, l]],
                    [self.Cl_fid[2, l], self.Cl_fid[1, l], 0],
                    [cltd_fid, 0, cldd_fid]])
                Cov_the = np.array([
                    [cl['tt'][l]+self.noise_T[l], cl['te'][l], 0.*math.sqrt(l*(l+1.))*cl['tp'][l]],
                    [cl['te'][l], cl['ee'][l]+self.noise_P[l], 0],
                    [cltd, 0, cldd+self.Nldd[l]]])

            # case without B modes nor lensing:
            else:
                Cov_obs = np.array([
                    [self.Cl_fid[0, l], self.Cl_fid[2, l]],
                    [self.Cl_fid[2, l], self.Cl_fid[1, l]]])
                Cov_the = np.array([
                    [cl['tt'][l]+self.noise_T[l], cl['te'][l]],
                    [cl['te'][l], cl['ee'][l]+self.noise_P[l]]])

            # get determinant of observational and theoretical covariance matrices
            det_obs = np.linalg.det(Cov_obs)
            det_the = np.linalg.det(Cov_the)

            # get determinant of mixed matrix (= sum of N theoretical
            # matrices with, in each of them, the nth column replaced
            # by that of the observational matrix)
            det_mix = 0.
            for i in range(num_modes):
                Cov_mix = np.copy(Cov_the)
                Cov_mix[:, i] = Cov_obs[:, i]
                det_mix += np.linalg.det(Cov_mix)

            chi2 += (2.*l+1.)*self.f_sky *\
                (det_mix/det_the + math.log(det_the/det_obs) - num_modes)

        return -chi2/2


###################################
# MPK TYPE LIKELIHOOD
# --> sdss, wigglez, etc.
###################################
class Likelihood_mpk(Likelihood):

    def __init__(self, path, data, command_line, common=False, common_dict={}):

        Likelihood.__init__(self, path, data, command_line)

        # require P(k) from class
        self.need_cosmo_arguments(data, {'output': 'mPk'})

        if common:
            self.add_common_knowledge(common_dict)

        try:
            self.use_halofit
        except:
            self.use_halofit = False

        if self.use_halofit:
            self.need_cosmo_arguments(data, {'non linear': 'halofit'})

        # read values of k (in h/Mpc)
        self.k_size = self.max_mpk_kbands_use-self.min_mpk_kbands_use+1
        self.mu_size = 1
        self.k = np.zeros((self.k_size), 'float64')
        self.kh = np.zeros((self.k_size), 'float64')

        datafile = open(self.data_directory+self.kbands_file, 'r')

        for i in range(self.num_mpk_kbands_full):
            line = datafile.readline()
            if i+2 > self.min_mpk_kbands_use and i < self.max_mpk_kbands_use:
                self.kh[i-self.min_mpk_kbands_use+1] = float(line.split()[0])
        datafile.close()

        khmax = self.kh[-1]

        # check if need hight value of k for giggleZ
        try:
            self.use_giggleZ
        except:
            self.use_giggleZ = False

        # Try a new model, with an additional nuisance parameter. Note
        # that the flag use_giggleZPP0 being True requires use_giggleZ
        # to be True as well. Note also that it is defined globally,
        # and not for every redshift bin.
        if self.use_giggleZ:
            try:
                self.use_giggleZPP0
            except:
                self.use_giggleZPP0 = False
        else:
            self.use_giggleZPP0 = False

        # If the flag use_giggleZPP0 is set to True, the nuisance parameters
        # P0_a, P0_b, P0_c and P0_d are expected.
        if self.use_giggleZPP0:
            if 'P0_a' not in data.get_mcmc_parameters(['nuisance']):
                raise io_mp.LikelihoodError(
                    "In likelihood %s. " % self.name +
                    "P0_a is not defined in the .param file, whereas this " +
                    "nuisance parameter is required when the flag " +
                    "'use_giggleZPP0' is set to true for WiggleZ")

        if self.use_giggleZ:
            datafile = open(self.data_directory+self.giggleZ_fidpk_file, 'r')

            line = datafile.readline()
            k = float(line.split()[0])
            line_number = 1
            while (k < self.kh[0]):
                line = datafile.readline()
                k = float(line.split()[0])
                line_number += 1
            ifid_discard = line_number-2
            while (k < khmax):
                line = datafile.readline()
                k = float(line.split()[0])
                line_number += 1
            datafile.close()
            self.k_fid_size = line_number-ifid_discard+1
            khmax = k

        if self.use_halofit:
            khmax *= 2

        # require k_max and z_max from the cosmological module
        self.need_cosmo_arguments(
            data, {'P_k_max_h/Mpc': khmax, 'z_max_pk': self.redshift})

        # read information on different regions in the sky
        try:
            self.has_regions
        except:
            self.has_regions = False

        if (self.has_regions):
            self.num_regions = len(self.used_region)
            self.num_regions_used = 0
            for i in range(self.num_regions):
                if (self.used_region[i]):
                    self.num_regions_used += 1
            if (self.num_regions_used == 0):
                raise io_mp.LikelihoodError(
                    "In likelihood %s. " % self.name +
                    "Mpk: no regions begin used in this data set")
        else:
            self.num_regions = 1
            self.num_regions_used = 1
            self.used_region = [True]

        # read window functions
        self.n_size = self.max_mpk_points_use-self.min_mpk_points_use+1

        self.window = np.zeros(
            (self.num_regions, self.n_size, self.k_size), 'float64')

        datafile = open(self.data_directory+self.windows_file, 'r')
        for i_region in range(self.num_regions):
            if self.num_regions > 1:
                line = datafile.readline()
            for i in range(self.num_mpk_points_full):
                line = datafile.readline()
                if (i+2 > self.min_mpk_points_use and
                        i < self.max_mpk_points_use):
                    for j in range(self.k_size):
                        self.window[i_region, i-self.min_mpk_points_use+1, j]=\
                            float(line.split()[j+self.min_mpk_kbands_use-1])
        datafile.close()

        # read measurements
        self.P_obs = np.zeros((self.num_regions, self.n_size), 'float64')
        self.P_err = np.zeros((self.num_regions, self.n_size), 'float64')

        datafile = open(self.data_directory+self.measurements_file, 'r')
        for i_region in range(self.num_regions):
            for i in range(2):
                line = datafile.readline()
            for i in range(self.num_mpk_points_full):
                line = datafile.readline()
                if (i+2 > self.min_mpk_points_use and
                        i < self.max_mpk_points_use):
                    self.P_obs[i_region, i-self.min_mpk_points_use+1] = \
                        float(line.split()[3])
                    self.P_err[i_region, i-self.min_mpk_points_use+1] = \
                        float(line.split()[4])
        datafile.close()

        # read covariance matrices
        try:
            self.covmat_file
            self.use_covmat = True
        except:
            self.use_covmat = False

        self.invcov = np.zeros(
            (self.num_regions, self.n_size, self.n_size), 'float64')

        if self.use_covmat:
            cov = np.zeros((self.n_size, self.n_size), 'float64')
            invcov_tmp = np.zeros((self.n_size, self.n_size), 'float64')

            datafile = open(self.data_directory+self.covmat_file, 'r')
            for i_region in range(self.num_regions):
                for i in range(1):
                    line = datafile.readline()
                for i in range(self.num_mpk_points_full):
                    line = datafile.readline()
                    if (i+2 > self.min_mpk_points_use and
                            i < self.max_mpk_points_use):
                        for j in range(self.num_mpk_points_full):
                            if (j+2 > self.min_mpk_points_use and
                                    j < self.max_mpk_points_use):
                                cov[i-self.min_mpk_points_use+1,
                                    j-self.min_mpk_points_use+1] =\
                                    float(line.split()[j])
                invcov_tmp = np.linalg.inv(cov)
                for i in range(self.n_size):
                    for j in range(self.n_size):
                        self.invcov[i_region, i, j] = invcov_tmp[i, j]
            datafile.close()
        else:
            for i_region in range(self.num_regions):
                for j in range(self.n_size):
                    self.invcov[i_region, j, j] = \
                        1./(self.P_err[i_region, j]**2)

        # read fiducial model
        if self.use_giggleZ:
            self.P_fid = np.zeros((self.k_fid_size), 'float64')
            self.k_fid = np.zeros((self.k_fid_size), 'float64')
            datafile = open(self.data_directory+self.giggleZ_fidpk_file, 'r')
            for i in range(ifid_discard):
                line = datafile.readline()
            for i in range(self.k_fid_size):
                line = datafile.readline()
                self.k_fid[i] = float(line.split()[0])
                self.P_fid[i] = float(line.split()[1])
            datafile.close()

        return

    def add_common_knowledge(self, common_dictionary):
        """
        Add to a class the content of a shared dictionary of attributes

        The purpose of this method is to set some attributes globally for a Pk
        likelihood, that are shared amongst all the redshift bins (in
        WiggleZ.data for instance, a few flags and numbers are defined that
        will be transfered to wigglez_a, b, c and d

        """
        for key, value in common_dictionary.iteritems():
            # First, check if the parameter exists already
            try:
                exec("self.%s" % key)
                warnings.warn(
                    "parameter %s from likelihood %s will be replaced by " +
                    "the common knowledge routine" % (key, self.name))
            except:
                if type(value) != type('foo'):
                    exec("self.%s = %s" % (key, value))
                else:
                    exec("self.%s = '%s'" % (key, value))

    # compute likelihood
    def loglkl(self, cosmo, data):

        # reduced Hubble parameter
        h = cosmo.h()

        # WiggleZ specific
        if self.use_scaling:
            # angular diameter distance at this redshift, in Mpc
            d_angular = cosmo.angular_distance(self.redshift)

            # radial distance at this redshift, in Mpc, is simply 1/H (itself
            # in Mpc^-1). Hz is an array, with only one element.
            r, Hz = cosmo.z_of_r([self.redshift])
            d_radial = 1/Hz[0]

            # scaling factor = (d_angular**2 * d_radial)^(1/3) for the
            # fiducial cosmology used in the data files of the observations
            # divided by the same quantity for the cosmology we are comparing with.
            # The fiducial values are stored in the .data files for
            # each experiment, and are truly in Mpc. Beware for a potential
            # difference with CAMB conventions here.
            scaling = pow(
                (self.d_angular_fid/d_angular)**2 *
                (self.d_radial_fid/d_radial), 1./3.)
        else:
            scaling = 1

        # get rescaled values of k in 1/Mpc
        self.k = self.kh*h*scaling

        # get P(k) at right values of k, convert it to (Mpc/h)^3 and rescale it
        P_lin = np.zeros((self.k_size), 'float64')

        # If the flag use_giggleZ is set to True, the power spectrum retrieved
        # from Class will get rescaled by the fiducial power spectrum given by
        # the GiggleZ N-body simulations CITE
        if self.use_giggleZ:
            P = np.zeros((self.k_fid_size), 'float64')
            for i in range(self.k_fid_size):
                P[i] = cosmo.pk(self.k_fid[i]*h, self.redshift)
                power = 0
                # The following create a polynome in k, which coefficients are
                # stored in the .data files of the experiments.
                for j in range(6):
                    power += self.giggleZ_fidpoly[j]*self.k_fid[i]**j
                # rescale P by fiducial model and get it in (Mpc/h)**3
                P[i] *= pow(10, power)*(h/scaling)**3/self.P_fid[i]

            if self.use_giggleZPP0:
                # Shot noise parameter addition to GiggleZ model. It should
                # recover the proper nuisance parameter, depending on the name.
                # I.e., Wigglez_A should recover P0_a, etc...
                tag = self.name[-2:]  # circle over "_a", "_b", etc...
                P0_value = data.mcmc_parameters['P0'+tag]['current'] *\
                    data.mcmc_parameters['P0'+tag]['scale']
                P_lin = np.interp(self.kh,self.k_fid,P+P0_value)
            else:
                # get P_lin by interpolation. It is still in (Mpc/h)**3
                P_lin = np.interp(self.kh, self.k_fid, P)

        else:
            # get rescaled values of k in 1/Mpc
            self.k = self.kh*h*scaling
            # get values of P(k) in Mpc**3
            for i in range(self.k_size):
                P_lin[i] = cosmo.pk(self.k[i], self.redshift)
            # get rescaled values of P(k) in (Mpc/h)**3
            P_lin *= (h/scaling)**3

        W_P_th = np.zeros((self.n_size), 'float64')

        # starting analytic marginalisation over bias

        # Define quantities living in all the regions possible. If only a few
        # regions are selected in the .data file, many elements from these
        # arrays will stay at 0.
        P_data_large = np.zeros(
            (self.n_size*self.num_regions_used), 'float64')
        W_P_th_large = np.zeros(
            (self.n_size*self.num_regions_used), 'float64')
        cov_dat_large = np.zeros(
            (self.n_size*self.num_regions_used), 'float64')
        cov_th_large = np.zeros(
            (self.n_size*self.num_regions_used), 'float64')

        normV = 0

        # infer P_th from P_lin. It is still in (Mpc/h)**3. TODO why was it
        # called P_lin in the first place ? Couldn't we use now P_th all the
        # way ?
        P_th = P_lin

        # Loop over all the available regions
        for i_region in range(self.num_regions):
            # In each region that was selected with the array of flags
            # self.used_region, define boundaries indices, and fill in the
            # corresponding windowed power spectrum. All the unused regions
            # will still be set to zero as from the initialization, which will
            # not contribute anything in the final sum.
            if self.used_region[i_region]:
                imin = i_region*self.n_size
                imax = (i_region+1)*self.n_size-1

                W_P_th = np.dot(self.window[i_region, :], P_th)
                for i in range(self.n_size):
                    P_data_large[imin+i] = self.P_obs[i_region, i]
                    W_P_th_large[imin+i] = W_P_th[i]
                    cov_dat_large[imin+i] = np.dot(
                        self.invcov[i_region, i, :],
                        self.P_obs[i_region, :])
                    cov_th_large[imin+i] = np.dot(
                        self.invcov[i_region, i, :],
                        W_P_th[:])

        # Explain what it is TODO
        normV += np.dot(W_P_th_large, cov_th_large)
        # Sort of bias TODO ?
        b_out = np.sum(W_P_th_large*cov_dat_large) / \
            np.sum(W_P_th_large*cov_th_large)

        # Explain this formula better, link to article ?
        chisq = np.dot(P_data_large, cov_dat_large) - \
            np.dot(W_P_th_large, cov_dat_large)**2/normV

        return -chisq/2


class Likelihood_sn(Likelihood):

    def __init__(self, path, data, command_line):

        Likelihood.__init__(self, path, data, command_line)

        # try and import pandas
        try:
            import pandas
        except ImportError:
            raise io_mp.MissingLibraryError(
                "This likelihood has a lot of IO manipulation. You have "
                "to install the 'pandas' library to use it. Please type:\n"
                "`(sudo) pip install pandas --user`")

        # check that every conflicting experiments is not present in the list
        # of tested experiments, in which case, complain
        if hasattr(self, 'conflicting_experiments'):
            for conflict in self.conflicting_experiments:
                if conflict in data.experiments:
                    raise io_mp.LikelihoodError(
                        'conflicting %s measurements, you can ' % conflict +
                        ' have either %s or %s ' % (self.name, conflict) +
                        'as an experiment, not both')

        # Read the configuration file, supposed to be called self.settings.
        # Note that we unfortunately can not
        # immediatly execute the file, as it is not formatted as strings.
        assert hasattr(self, 'settings') is True, (
            "You need to provide a settings file")
        self.read_configuration_file()

    def read_configuration_file(self):
        """
        Extract Python variables from the configuration file

        This routine performs the equivalent to the program "inih" used in the
        original c++ library.
        """
        settings_path = os.path.join(self.data_directory, self.settings)
        with open(settings_path, 'r') as config:
            for line in config:
                # Dismiss empty lines and commented lines
                if line and line.find('#') == -1 and line not in ['\n', '\r\n']:
                    lhs, rhs = [elem.strip() for elem in line.split('=')]
                    # lhs will always be a string, so set the attribute to this
                    # likelihood. The right hand side requires more work.
                    # First case, if set to T or F for True or False
                    if str(rhs) in ['T', 'F']:
                        rhs = True if str(rhs) == 'T' else False
                    # It can also be a path, starting with 'data/'. We remove
                    # this leading folder path
                    elif str(rhs).find('data/') != -1:
                        rhs = rhs.replace('data/', '')
                    else:
                        # Try  to convert it to a float
                        try:
                            rhs = float(rhs)
                        # If it fails, it is a string
                        except ValueError:
                            rhs = str(rhs)
                    # Set finally rhs to be a parameter of the class
                    setattr(self, lhs, rhs)

    def read_matrix(self, path):
        """
        extract the matrix from the path

        This routine uses the blazing fast pandas library (0.10 seconds to load
        a 740x740 matrix). If not installed, it uses a custom routine that is
        twice as slow (but still 4 times faster than the straightforward
        numpy.loadtxt method)

        .. note::

            the length of the matrix is stored on the first line... then it has
            to be unwrapped. The pandas routine read_table understands this
            immediatly, though.

        """
        from pandas import read_table
        path = os.path.join(self.data_directory, path)
        # The first line should contain the length.
        with open(path, 'r') as text:
            length = int(text.readline())

        # Note that this function does not require to skiprows, as it
        # understands the convention of writing the length in the first
        # line
        matrix = read_table(path).as_matrix().reshape((length, length))

        return matrix

    def read_light_curve_parameters(self):
        """
        Read the file jla_lcparams.txt containing the SN data

        .. note::

            the length of the resulting array should be equal to the length of
            the covariance matrices stored in C00, etc...

        """
        from pandas import read_table
        path = os.path.join(self.data_directory, self.data_file)

        # Recover the names of the columns. The names '3rdvar' and 'd3rdvar'
        # will be changed, because 3rdvar is not a valid variable name
        with open(path, 'r') as text:
            clean_first_line = text.readline()[1:].strip()
            names = [e.strip().replace('3rd', 'third')
                     for e in clean_first_line.split()]

        lc_parameters = read_table(
            path, sep=' ', names=names, header=0, index_col=False)
        return lc_parameters


class Likelihood_clocks(Likelihood):
    """Base implementation of H(z) measurements"""

    def __init__(self, path, data, command_line):

        Likelihood.__init__(self, path, data, command_line)

        # Read the content of the data file, containing z, Hz and error
        total = np.loadtxt(
            os.path.join(self.data_directory, self.data_file))

        # Store the columns separately
        self.z = total[:, 0]
        self.Hz = total[:, 1]
        self.err = total[:, 2]

    def loglkl(self, cosmo, data):

        # Store the speed of light in km/s
        c_light_km_per_sec = const.c/1000.
        chi2 = 0

        # Loop over the redshifts
        for index, z in enumerate(self.z):
            # Query the cosmo module for the Hubble rate (in 1/Mpc), and
            # convert it to km/s/Mpc
            H_cosmo = cosmo.Hubble(z)*c_light_km_per_sec
            # Add to the tota chi2
            chi2 += (self.Hz[index]-H_cosmo)**2/self.err[index]**2

        return -0.5 * chi2
