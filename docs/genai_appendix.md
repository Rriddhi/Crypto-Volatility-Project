# Generative AI Tools Usage Appendix

## Introduction

This project utilized generative AI tools (primarily Cursor and ChatGPT) to accelerate development, code generation, and documentation. These tools were used as coding assistants to help with boilerplate code, complex configurations, documentation structure, and debugging. All AI-generated code and documentation was reviewed, tested, and modified by the student to ensure correctness, alignment with project requirements, and understanding of the implementation.

---

## AI-Assisted Development Entries

### Infrastructure & Docker

#### Docker Compose Configuration
- **Prompt (summary):** "Generate docker/compose.yaml for Kafka + MLflow in KRaft mode with proper networking and volume configuration"
- **Used in:**
  - `docker/compose.yaml`
- **Verification:** 
  - Tested Kafka container startup and connectivity from host
  - Verified MLflow UI accessibility on port 5001
  - Confirmed KRaft mode configuration (no ZooKeeper dependency)
  - Validated volume mounts and network isolation
  - Tested topic creation and message publishing/consumption

---

### Data Ingestion

#### WebSocket Ingestion Script
- **Prompt (summary):** "Create a WebSocket client script to ingest Coinbase Advanced Trade ticker data, publish to Kafka, and save raw data to NDJSON files with error handling and reconnection logic"
- **Used in:**
  - `scripts/ws_ingest.py`
- **Verification:**
  - Tested WebSocket connection to Coinbase API
  - Validated message parsing and JSON structure handling
  - Verified Kafka producer integration and message publishing
  - Tested NDJSON file writing with date-based file naming
  - Confirmed graceful shutdown and reconnection logic
  - Validated error handling for network failures and API errors

---

### Feature Engineering

#### Feature Calculator & Featurizer
- **Prompt (summary):** "Implement rolling window feature computation for crypto volatility prediction including midprice, returns, rolling volatility, spread, and trade intensity with Kafka consumer/producer integration"
- **Used in:**
  - `features/featurizer.py`
  - `features/extractors/` (if applicable)
  - `features/transformers/` (if applicable)
- **Verification:**
  - Validated rolling window calculations match feature specification
  - Tested feature computation on sample data
  - Verified Parquet output format and schema
  - Confirmed Kafka integration (consumer and producer)
  - Tested edge cases (missing data, window initialization)
  - Compared feature outputs with manual calculations

#### Replay Script
- **Prompt (summary):** "Create a replay script to regenerate features from saved NDJSON files, ensuring bit-for-bit identical output to live feature computation"
- **Used in:**
  - `scripts/replay.py`
- **Verification:**
  - Tested replay on historical NDJSON files
  - Compared `features.parquet` (live) vs `features_replay.parquet` (replay)
  - Validated feature consistency and reproducibility
  - Confirmed timestamp handling and data ordering
  - Tested with various date ranges and file sizes

---

### Modeling

#### Training Script
- **Prompt (summary):** "Create a training script for baseline rule model and ML model (LogisticRegression/XGBoost) with MLflow tracking, train/val/test splits, and evaluation metrics (PR-AUC, F1)"
- **Used in:**
  - `models/train.py`
- **Verification:**
  - Tested data loading and splitting logic
  - Validated baseline model threshold calculation
  - Verified ML model training and hyperparameter configuration
  - Confirmed MLflow logging (metrics, parameters, artifacts)
  - Tested evaluation metrics computation
  - Validated model serialization and artifact saving
  - Tested with different threshold values and model types

#### Inference Script
- **Prompt (summary):** "Create an inference script to load trained models and generate predictions on new data with optional evaluation logging to MLflow"
- **Used in:**
  - `models/infer.py`
- **Verification:**
  - Tested model loading from pickle files
  - Validated prediction generation on test data
  - Verified feature preparation matches training pipeline
  - Confirmed MLflow evaluation logging (if implemented)
  - Tested with both baseline and ML models
  - Validated prediction format and probability outputs

---

### Monitoring & Reporting

#### Evidently Report Generation
- **Prompt (summary):** "Create a script to generate Evidently AI reports for data drift, data quality, and train/test distribution comparison with HTML and JSON outputs"
- **Used in:**
  - `reports/generate_evidently.py`
- **Verification:**
  - Tested report generation on training and test datasets
  - Validated drift detection metrics
  - Confirmed HTML report rendering and accessibility
  - Tested JSON output for programmatic access
  - Verified comparison modes (train/test, early/late)
  - Validated feature distribution visualizations

---

### Documentation

#### Scoping Brief
- **Prompt (summary):** "Create a scoping brief document outlining the crypto volatility prediction project, objectives, architecture, and milestones"
- **Used in:**
  - `docs/scoping_brief.md`
- **Verification:**
  - Reviewed and refined project scope and objectives
  - Updated architecture diagrams and component descriptions
  - Validated milestone definitions and deliverables
  - Ensured alignment with assignment requirements

#### Feature Specification
- **Prompt (summary):** "Create a comprehensive feature specification document describing data sources, feature definitions, target variable, preprocessing steps, and validation requirements"
- **Used in:**
  - `docs/feature_spec.md`
- **Verification:**
  - Cross-referenced with actual feature implementation
  - Validated formulas and calculations
  - Updated threshold values based on EDA results
  - Confirmed feature schema matches code output
  - Reviewed data quality assumptions and handling

#### Model Evaluation Report
- **Prompt (summary):** "Create a model evaluation report template with sections for baseline and ML model performance, comparison metrics, drift analysis, and next steps"
- **Used in:**
  - `reports/model_eval.md`
- **Verification:**
  - Reviewed template structure and completeness
  - Updated with actual metrics from MLflow runs (where available)
  - Validated metric definitions and interpretations
  - Ensured alignment with evaluation methodology

#### Model Card
- **Prompt (summary):** "Create a model card document following standard structure with model details, intended use, data description, performance metrics, ethical considerations, and limitations"
- **Used in:**
  - `docs/model_card_v1.md`
- **Verification:**
  - Reviewed model card structure against industry standards
  - Validated technical accuracy of model descriptions
  - Ensured comprehensive coverage of limitations and risks
  - Confirmed alignment with project implementation

#### Architecture Documentation
- **Prompt (summary):** "Create architecture documentation describing system components, data flow, and technology stack"
- **Used in:**
  - `docs/architecture.md`
- **Verification:**
  - Cross-referenced with actual implementation
  - Validated component descriptions and interactions
  - Updated diagrams and data flow descriptions
  - Confirmed technology choices and rationale

#### API Documentation
- **Prompt (summary):** "Document API endpoints, message formats, and integration patterns for the data ingestion and feature pipeline"
- **Used in:**
  - `docs/api.md`
- **Verification:**
  - Tested API examples against actual implementation
  - Validated message format specifications
  - Confirmed endpoint descriptions and usage patterns

#### Pipeline Documentation
- **Prompt (summary):** "Document the end-to-end pipeline workflow from data ingestion through feature engineering to model training and inference"
- **Used in:**
  - `docs/pipeline.md`
- **Verification:**
  - Validated workflow steps against actual scripts
  - Confirmed data flow and transformation steps
  - Updated with actual configuration and parameters

#### Setup Documentation
- **Prompt (summary):** "Create setup and installation documentation with environment requirements, Docker setup, and configuration instructions"
- **Used in:**
  - `docs/setup.md`
- **Verification:**
  - Tested setup instructions on clean environment
  - Validated dependency versions and installation steps
  - Confirmed Docker commands and configuration
  - Updated with troubleshooting notes from actual experience

---

## Additional AI Assistance

### Code Review & Debugging
- **Usage:** AI tools were used to help debug Kafka connectivity issues, WebSocket reconnection logic, feature computation edge cases, and MLflow integration problems
- **Verification:** All fixes were tested and validated before integration

### Code Refactoring
- **Usage:** AI assistance was used to improve code structure, add error handling, and enhance logging throughout the project
- **Verification:** Refactored code was tested to ensure functionality preservation

### Testing & Validation
- **Usage:** AI tools helped generate test cases and validation logic for feature consistency checks
- **Verification:** All tests were run and validated against expected behavior

---

## Responsibility Statement

**I, the student, am fully responsible for:**

1. **Code Validation:** All AI-generated code was reviewed, tested, and modified as needed. I understand how each component works and can explain the implementation.

2. **Documentation Accuracy:** All documentation was reviewed and updated to reflect the actual implementation. I ensured technical accuracy and completeness.

3. **Project Understanding:** I have a comprehensive understanding of the entire system architecture, data flow, feature engineering pipeline, and model implementation.

4. **Testing & Verification:** All code and documentation were tested and validated through:
   - Manual code review
   - Execution and testing of scripts
   - Validation of outputs against specifications
   - Comparison of results with expected behavior

5. **Academic Integrity:** While AI tools were used as assistants, all work represents my understanding and implementation. I am responsible for the correctness, quality, and academic integrity of the final deliverables.

6. **Future Maintenance:** I am capable of maintaining, debugging, and extending the codebase without relying on AI tools, as I understand the implementation details.

---

**Document Status:** Complete  
**Last Updated:** 2025-11-17

