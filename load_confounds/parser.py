"""Flexible method to load confounds generated by fMRIprep.

Authors: load_confounds team
"""
import numpy as np
import pandas as pd
from . import confounds as cf
from .compcor import _find_compcor

# Global variables listing the admissible types of noise components
all_confounds = [
    "motion",
    "high_pass",
    "wm_csf",
    "global",
    "compcor",
    "ica_aroma",
    "scrub",
]


def _sanitize_strategy(strategy):
    """Defines the supported denoising strategies."""
    if isinstance(strategy, list):
        for conf in strategy:
            if not conf in all_confounds:
                raise ValueError(f"{conf} is not a supported type of confounds.")
    else:
        raise ValueError("strategy needs to be a list of strings")
    return strategy


def _check_error(missing_confounds, missing_keys):
    """Consolidate a single error message across multiple missing confounds."""
    if missing_confounds or missing_keys:
        error_msg = (
            "The following keys or parameters are missing: "
            + f" {missing_confounds}"
            + f" {missing_keys}"
            + ". You may want to try a different denoising strategy."
        )
        raise ValueError(error_msg)


class Confounds:
    """
    Confounds from fmriprep

    Parameters
    ----------
    strategy : list of strings
        The type of noise confounds to include.
        "motion" head motion estimates.
        "high_pass" discrete cosines covering low frequencies.
        "wm_csf" confounds derived from white matter and cerebrospinal fluid.
        "global" confounds derived from the global signal.
        "ica_aroma" confounds derived from ICA-AROMA.
        "scrub" regressors for Power 2014 scrubbing approach.

    motion : string, optional
        Type of confounds extracted from head motion estimates.
        "basic" translation/rotation (6 parameters)
        "power2" translation/rotation + quadratic terms (12 parameters)
        "derivatives" translation/rotation + derivatives (12 parameters)
        "full" translation/rotation + derivatives + quadratic terms + power2d derivatives (24 parameters)

    n_motion : float
        Number of pca components to keep from head motion estimates.
        If the parameters is strictly comprised between 0 and 1, a principal component
        analysis is applied to the motion parameters, and the number of extracted
        components is set to exceed `n_motion` percent of the parameters variance.
        If the n_components = 0, then no PCA is performed.

    fd_thresh : float, optional
        Framewise displacement threshold for scrub (default = 0.2 mm)

    std_dvars_thresh : float, optional
        Standardized DVARS threshold for scrub (default = 3)

    wm_csf : string, optional
        Type of confounds extracted from masks of white matter and cerebrospinal fluids.
        "basic" the averages in each mask (2 parameters)
        "power2" averages and quadratic terms (4 parameters)
        "derivatives" averages and derivatives (4 parameters)
        "full" averages + derivatives + quadratic terms + power2d derivatives (8 parameters)

    global_signal : string, optional
        Type of confounds extracted from the global signal.
        "basic" just the global signal (1 parameter)
        "power2" global signal and quadratic term (2 parameters)
        "derivatives" global signal and derivative (2 parameters)
        "full" global signal + derivatives + quadratic terms + power2d derivatives (4 parameters)

    scrub : string, optional
        Type of scrub of frames with excessive motion (Power et al. 2014)
        "basic" remove time frames based on excessive FD and DVARS
        "full" also remove time windows which are too short after scrubbing.
        one-hot encoding vectors are added as regressors for each scrubbed frame.

    compcor : string, optional
        Type of confounds extracted from a component based noise correction method
        "anat" noise components calculated using anatomical compcor
        "temp" noise components calculated using temporal compcor
        "full" noise components calculated using both temporal and anatomical

    n_compcor : int or "auto", optional
        The number of noise components to be extracted. For acompcor_combined=False,
        and/or compcor="full", this is the number of components per mask.
        Default is "auto": select all components (50% variance explained by fMRIPrep defaults)

    acompcor_combined: boolean, optional
        If true, use components generated from the combined white matter and csf
        masks. Otherwise, components are generated from each mask separately and then
        concatenated.

    ica_aroma : None or string, optional
        None: default, not using ICA-AROMA related strategy
        "basic": use noise IC only.
        "full": use fMRIprep output `~desc-smoothAROMAnonaggr_bold.nii.gz` .

    demean : boolean, optional
        If True, the confounds are standardized to a zero mean (over time).
        This step is critical if the confounds are regressed out of time series
        using nilearn with no or zscore standardization, but should be turned off
        with "spc" normalization.

    Attributes
    ----------
    `confounds_` : ndarray
        The confounds loaded using the specified model

    `columns_`: list of str
        The labels of the different confounds

    Notes
    -----
    The predefined strategies implemented in this class are
    adapted from (Ciric et al. 2017). Band-pass filter is replaced
    by high-pass filter. Low-pass filters can be implemented, e.g., through
    nilearn maskers. Scrubbing is implemented by introducing regressors in the
    confounds, rather than eliminating time points. Other aspects of the
    preprocessing listed in Ciric et al. (2017) are controlled through fMRIprep,
    e.g. distortion correction.

    References
    ----------
    Ciric et al., 2017 "Benchmarking of participant-level confound regression
    strategies for the control of motion artifact in studies of functional
    connectivity" Neuroimage 154: 174-87
    https://doi.org/10.1016/j.neuroimage.2017.03.020
    """

    def __init__(
        self,
        strategy=["motion", "high_pass", "wm_csf"],
        motion="full",
        n_motion=0,
        scrub="full",
        fd_thresh=0.2,
        std_dvars_thresh=3,
        wm_csf="basic",
        global_signal="basic",
        compcor="anat",
        acompcor_combined=True,
        n_compcor="auto",
        ica_aroma=None,
        demean=True,
    ):
        """Default parameters."""
        self.strategy = _sanitize_strategy(strategy)
        self.motion = motion
        self.n_motion = n_motion
        self.scrub = scrub
        self.fd_thresh = fd_thresh
        self.std_dvars_thresh = std_dvars_thresh
        self.wm_csf = wm_csf
        self.global_signal = global_signal
        self.compcor = compcor
        self.acompcor_combined = acompcor_combined
        self.n_compcor = n_compcor
        self.ica_aroma = ica_aroma
        self.demean = demean

    def load(self, img_files):
        """
        Load fMRIprep confounds

        Parameters
        ----------
        img_files : path to processed image files, optionally as a list.
            Processed nii.gz/dtseries.nii/func.gii file from fmriprep.
            `nii.gz` or `dtseries.nii`: path to files, optionally as a list.
            `func.gii`: list of a pair of paths to files, optionally as a list of lists.
            The companion tsv will be automatically detected.

        Returns
        -------
        confounds :  ndarray or list of ndarray
            A reduced version of fMRIprep confounds based on selected strategy and flags.
            An intercept is automatically added to the list of confounds.
        """
        img_files, flag_single = cf._sanitize_confounds(img_files)
        confounds_out = []
        columns_out = []
        self.missing_confounds_ = []
        self.missing_keys_ = []

        for file in img_files:
            conf, col = self._load_single(file)
            confounds_out.append(conf)
            columns_out.append(col)

        # If a single input was provided,
        # send back a single output instead of a list
        if flag_single:
            confounds_out = confounds_out[0]
            columns_out = columns_out[0]

        self.confounds_ = confounds_out
        self.columns_ = columns_out
        return confounds_out

    def _load_single(self, confounds_raw):
        """Load a single confounds file from fmriprep."""
        # Convert tsv file to pandas dataframe
        # check if relevant imaging files are present according to the strategy
        flag_acompcor = ("compcor" in self.strategy) and (self.compcor == "anat")
        flag_full_aroma = ("ica_aroma" in self.strategy) and (self.ica_aroma == "full")
        confounds_raw, self.json_ = cf._confounds_to_df(
            confounds_raw, flag_acompcor, flag_full_aroma
        )

        confounds = pd.DataFrame()

        for confound in self.strategy:
            loaded_confounds = self._load_confound(confounds_raw, confound)
            confounds = pd.concat([confounds, loaded_confounds], axis=1)

        _check_error(self.missing_confounds_, self.missing_keys_)
        confounds, labels = cf._confounds_to_ndarray(confounds, self.demean)
        return confounds, labels

    def _load_confound(self, confounds_raw, confound):
        """Load a single type of confound."""
        try:
            loaded_confounds = getattr(self, f"_load_{confound}")(confounds_raw)
        except cf.MissingConfound as exception:
            self.missing_confounds_ += exception.params
            self.missing_keys_ += exception.keywords
            loaded_confounds = pd.DataFrame()
        return loaded_confounds

    def _load_motion(self, confounds_raw):
        """Load the motion regressors."""
        motion_params = cf._add_suffix(
            ["trans_x", "trans_y", "trans_z", "rot_x", "rot_y", "rot_z"], self.motion
        )
        cf._check_params(confounds_raw, motion_params)
        confounds_motion = confounds_raw[motion_params]

        # Optionally apply PCA reduction
        if self.n_motion > 0:
            confounds_motion = cf._pca_motion(
                confounds_motion, n_components=self.n_motion
            )
        return confounds_motion

    def _load_high_pass(self, confounds_raw):
        """Load the high pass filter regressors."""
        high_pass_params = cf._find_confounds(confounds_raw, ["cosine"])
        return confounds_raw[high_pass_params]

    def _load_wm_csf(self, confounds_raw):
        """Load the regressors derived from the white matter and CSF masks."""
        wm_csf_params = cf._add_suffix(["csf", "white_matter"], self.wm_csf)
        cf._check_params(confounds_raw, wm_csf_params)
        return confounds_raw[wm_csf_params]

    def _load_global(self, confounds_raw):
        """Load the regressors derived from the global signal."""
        global_params = cf._add_suffix(["global_signal"], self.global_signal)
        cf._check_params(confounds_raw, global_params)
        return confounds_raw[global_params]

    def _load_compcor(self, confounds_raw):
        """Load compcor regressors."""
        compcor_cols = _find_compcor(
            self.json_, self.compcor, self.n_compcor, self.acompcor_combined
        )
        cf._check_params(confounds_raw, compcor_cols)
        return confounds_raw[compcor_cols]

    def _load_ica_aroma(self, confounds_raw):
        """Load the ICA-AROMA regressors."""
        if self.ica_aroma is None:
            raise ValueError("Please select an option when using ICA-AROMA strategy")
        if self.ica_aroma == "full":
            return pd.DataFrame()
        if self.ica_aroma == "basic":
            ica_aroma_params = cf._find_confounds(confounds_raw, ["aroma"])
            return confounds_raw[ica_aroma_params]

    def _load_scrub(self, confounds_raw):
        """Perform basic scrub - Remove volumes if framewise displacement exceeds threshold."""
        n_scans = len(confounds_raw)
        # Get indices of fd outliers
        fd_outliers = np.where(
            confounds_raw["framewise_displacement"] > self.fd_thresh
        )[0]
        dvars_outliers = np.where(confounds_raw["std_dvars"] > self.std_dvars_thresh)[0]
        combined_outliers = np.sort(
            np.unique(np.concatenate((fd_outliers, dvars_outliers)))
        )
        # Do full scrubbing if desired, and motion outliers were detected
        if self.scrub == "full" and len(combined_outliers) > 0:
            combined_outliers = cf._optimize_scrub(combined_outliers, n_scans)
        # Make one-hot encoded motion outlier regressors
        motion_outlier_regressors = pd.DataFrame(
            np.transpose(np.eye(n_scans)[combined_outliers]).astype(int)
        )
        column_names = [
            "motion_outlier_" + str(num)
            for num in range(np.shape(motion_outlier_regressors)[1])
        ]
        motion_outlier_regressors.columns = column_names
        return motion_outlier_regressors
