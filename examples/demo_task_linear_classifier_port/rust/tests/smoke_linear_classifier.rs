use linear_classifier::{
    confusion_matrix, cross_entropy_loss, expected_calibration_error, macro_f1, new_linear_classifier,
    per_class_metrics, predict_batch, predict_proba_batch, predict_top_k,
};

#[test]
fn predict_batch_and_top_k_match_expected_labels() {
    let model = new_linear_classifier(
        vec![
            vec![1.5, -0.5],
            vec![-0.5, 1.0],
            vec![0.2, 0.3],
        ],
        vec![0.1, -0.2, 0.0],
    )
    .unwrap();
    let features = vec![vec![2.0, 0.0], vec![0.0, 2.0], vec![1.0, 1.0]];

    let probabilities = predict_proba_batch(&model, &features).unwrap();
    let labels = predict_batch(&probabilities).unwrap();
    let top_k = predict_top_k(&probabilities, 2).unwrap();

    assert_eq!(labels, vec![0, 1, 0]);
    assert_eq!(top_k, vec![vec![0, 2], vec![1, 2], vec![0, 1]]);
}

#[test]
fn cross_entropy_and_report_metrics_are_reasonable() {
    let probabilities = vec![
        vec![0.80, 0.15, 0.05],
        vec![0.10, 0.75, 0.15],
        vec![0.45, 0.45, 0.10],
        vec![0.05, 0.10, 0.85],
    ];
    let targets = vec![0, 1, 1, 2];

    let loss = cross_entropy_loss(&probabilities, &targets).unwrap();
    assert!(loss > 0.0);
    assert!(loss < 1.0);

    let matrix = confusion_matrix(&probabilities, &targets).unwrap();
    assert_eq!(matrix, vec![vec![1, 0, 0], vec![1, 1, 0], vec![0, 0, 1]]);

    let report = per_class_metrics(&matrix).unwrap();
    let macro_score = macro_f1(&report).unwrap();
    assert!((macro_score - (7.0 / 9.0)).abs() < 1e-12);
}

#[test]
fn expected_calibration_error_is_small_for_confident_correct_predictions() {
    let probabilities = vec![
        vec![0.90, 0.05, 0.05],
        vec![0.10, 0.80, 0.10],
        vec![0.05, 0.10, 0.85],
        vec![0.70, 0.20, 0.10],
    ];
    let targets = vec![0, 1, 2, 0];

    let ece = expected_calibration_error(&probabilities, &targets, 5).unwrap();
    assert!(ece >= 0.0);
    assert!(ece < 0.2);
}
