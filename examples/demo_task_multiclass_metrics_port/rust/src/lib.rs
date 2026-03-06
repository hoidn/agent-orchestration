use std::error::Error;
use std::fmt;

#[derive(Debug, Clone, PartialEq)]
pub struct ClassMetrics {
    pub precision: f64,
    pub recall: f64,
    pub f1: f64,
    pub support: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum MetricsError {
    EmptyProbabilities,
    EmptyProbabilityRow,
    RaggedProbabilities,
    TargetLengthMismatch,
    TargetOutOfRange,
    InvalidK,
    NumClassesMismatch,
    EmptyConfusion,
    NonSquareConfusion,
    InvalidBinCount,
}

impl fmt::Display for MetricsError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let message = match self {
            MetricsError::EmptyProbabilities => "probabilities must not be empty",
            MetricsError::EmptyProbabilityRow => "probability rows must not be empty",
            MetricsError::RaggedProbabilities => "probability rows must all have the same length",
            MetricsError::TargetLengthMismatch => "targets length must match probabilities length",
            MetricsError::TargetOutOfRange => "target class id out of range",
            MetricsError::InvalidK => "k must be between 1 and the number of classes",
            MetricsError::NumClassesMismatch => "num_classes must match the probability row width",
            MetricsError::EmptyConfusion => "confusion matrix must not be empty",
            MetricsError::NonSquareConfusion => "confusion matrix must be square",
            MetricsError::InvalidBinCount => "num_bins must be positive",
        };
        write!(f, "{message}")
    }
}

impl Error for MetricsError {}

pub fn top_k_accuracy(
    _probabilities: &[Vec<f64>],
    _targets: &[usize],
    _k: usize,
) -> Result<f64, MetricsError> {
    unimplemented!("port the Python reference implementation")
}

pub fn confusion_matrix(
    _probabilities: &[Vec<f64>],
    _targets: &[usize],
    _num_classes: usize,
) -> Result<Vec<Vec<usize>>, MetricsError> {
    unimplemented!("port the Python reference implementation")
}

pub fn per_class_metrics(_confusion: &[Vec<usize>]) -> Result<Vec<ClassMetrics>, MetricsError> {
    unimplemented!("port the Python reference implementation")
}

pub fn macro_f1(_report: &[ClassMetrics]) -> Result<f64, MetricsError> {
    unimplemented!("port the Python reference implementation")
}

pub fn expected_calibration_error(
    _probabilities: &[Vec<f64>],
    _targets: &[usize],
    _num_bins: usize,
) -> Result<f64, MetricsError> {
    unimplemented!("port the Python reference implementation")
}
