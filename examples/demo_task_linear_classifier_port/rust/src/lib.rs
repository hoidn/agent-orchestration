use std::error::Error;
use std::fmt;

#[derive(Debug, Clone, PartialEq)]
pub struct LinearClassifier {
    pub weights: Vec<Vec<f64>>,
    pub bias: Vec<f64>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ClassMetrics {
    pub precision: f64,
    pub recall: f64,
    pub f1: f64,
    pub support: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ClassifierError {
    EmptyWeights,
    EmptyWeightRow,
    RaggedWeights,
    BiasLengthMismatch,
    EmptyFeatures,
    FeatureWidthMismatch,
    EmptyProbabilities,
    EmptyProbabilityRow,
    RaggedProbabilities,
    TargetLengthMismatch,
    TargetOutOfRange,
    InvalidK,
    EmptyConfusion,
    NonSquareConfusion,
    InvalidBinCount,
    NonPositiveTrueClassProbability,
}

impl fmt::Display for ClassifierError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let message = match self {
            ClassifierError::EmptyWeights => "weights must not be empty",
            ClassifierError::EmptyWeightRow => "weight rows must not be empty",
            ClassifierError::RaggedWeights => "weight rows must all have the same length",
            ClassifierError::BiasLengthMismatch => "bias length must match the number of classes",
            ClassifierError::EmptyFeatures => "features must not be empty",
            ClassifierError::FeatureWidthMismatch => "feature row width must match the model",
            ClassifierError::EmptyProbabilities => "probabilities must not be empty",
            ClassifierError::EmptyProbabilityRow => "probability rows must not be empty",
            ClassifierError::RaggedProbabilities => "probability rows must all have the same length",
            ClassifierError::TargetLengthMismatch => "targets length must match features length",
            ClassifierError::TargetOutOfRange => "target class id out of range",
            ClassifierError::InvalidK => "k must be between 1 and the number of classes",
            ClassifierError::EmptyConfusion => "confusion matrix must not be empty",
            ClassifierError::NonSquareConfusion => "confusion matrix must be square",
            ClassifierError::InvalidBinCount => "num_bins must be positive",
            ClassifierError::NonPositiveTrueClassProbability => "true-class probability must be positive",
        };
        write!(f, "{message}")
    }
}

impl Error for ClassifierError {}

pub fn new_linear_classifier(
    _weights: Vec<Vec<f64>>,
    _bias: Vec<f64>,
) -> Result<LinearClassifier, ClassifierError> {
    unimplemented!("port the Python reference implementation")
}

pub fn predict_proba_batch(
    _model: &LinearClassifier,
    _features: &[Vec<f64>],
) -> Result<Vec<Vec<f64>>, ClassifierError> {
    unimplemented!("port the Python reference implementation")
}

pub fn predict_batch(
    _probabilities: &[Vec<f64>],
) -> Result<Vec<usize>, ClassifierError> {
    unimplemented!("port the Python reference implementation")
}

pub fn predict_top_k(
    _probabilities: &[Vec<f64>],
    _k: usize,
) -> Result<Vec<Vec<usize>>, ClassifierError> {
    unimplemented!("port the Python reference implementation")
}

pub fn cross_entropy_loss(
    _probabilities: &[Vec<f64>],
    _targets: &[usize],
) -> Result<f64, ClassifierError> {
    unimplemented!("port the Python reference implementation")
}

pub fn confusion_matrix(
    _probabilities: &[Vec<f64>],
    _targets: &[usize],
) -> Result<Vec<Vec<usize>>, ClassifierError> {
    unimplemented!("port the Python reference implementation")
}

pub fn per_class_metrics(
    _confusion: &[Vec<usize>],
) -> Result<Vec<ClassMetrics>, ClassifierError> {
    unimplemented!("port the Python reference implementation")
}

pub fn macro_f1(_report: &[ClassMetrics]) -> Result<f64, ClassifierError> {
    unimplemented!("port the Python reference implementation")
}

pub fn expected_calibration_error(
    _probabilities: &[Vec<f64>],
    _targets: &[usize],
    _num_bins: usize,
) -> Result<f64, ClassifierError> {
    unimplemented!("port the Python reference implementation")
}
