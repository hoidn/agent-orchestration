use std::error::Error;
use std::fmt;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SlidingWindowError {
    EmptyValues,
    InvalidWindowSize,
    InvalidStride,
    ConflictingTailMode,
}

impl fmt::Display for SlidingWindowError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let message = match self {
            SlidingWindowError::EmptyValues => "values must not be empty",
            SlidingWindowError::InvalidWindowSize => "window_size must be positive",
            SlidingWindowError::InvalidStride => "stride must be positive",
            SlidingWindowError::ConflictingTailMode => "pad_value must be None when drop_last is true",
        };
        write!(f, "{message}")
    }
}

impl Error for SlidingWindowError {}

pub fn window_start_indices(
    _values: &[f64],
    _window_size: usize,
    _stride: usize,
    _drop_last: bool,
    _pad_value: Option<f64>,
) -> Result<Vec<usize>, SlidingWindowError> {
    unimplemented!("port the Python reference implementation")
}

pub fn sliding_windows(
    _values: &[f64],
    _window_size: usize,
    _stride: usize,
    _drop_last: bool,
    _pad_value: Option<f64>,
) -> Result<Vec<Vec<f64>>, SlidingWindowError> {
    unimplemented!("port the Python reference implementation")
}
