## Project Design and Principles: Mushroom Automation System V2

**Document Version:** 1.2
**Last Updated:** 2025-05-07

**1. Introduction & Vision**

To create a robust, configurable, and extensible system for automating the environmental control and monitoring of a mushroom growing setup. The system aims to be reliable, maintainable, and designed to support future enhancements, including advanced control algorithms and comprehensive data analysis capabilities.

**2. Core Project Goals & Key Objectives**

- **(Derived from GovLayerDoc 1.2 & other docs)**
The primary goal is to transition from any fragmented V1 configurations and approaches to a validated Single Source of Truth (SSOT) for the entire Mushroom Automation System V2. This system should empower efficient and effective mushroom cultivation through precise environmental control.
    
    Key objectives to achieve this goal include:
    
    - **Configuration-Driven:** The entire system behavior – encompassing hardware mapping, control logic execution, data flow, and component interactions – must be defined through clear, human-readable, and machine-parseable configuration files. These files will collectively act as the Single Source of Truth (SSOT).
    - **Automated Build & Deployment:** Streamline and automate the build, testing, and deployment processes for all layers of the system (Microcontroller, Driver, Governor, Data Processing).
    - **Improved Code Quality & Python Best Practices:** Continuously improve overall code quality based on lessons learned from V1 and ongoing development. Adhere to modern Python standards, including robust error handling, improved file management, proper packaging, clear import strategies, and effective use of type hinting. Leverage well-regarded libraries like Pydantic for configuration and data validation.
    - **Modular & Extensible Architecture:** Design and maintain a layered architecture (Microcontroller, Driver, Data Processing Layer, Governor) that promotes separation of concerns.
    - **Refactored Driver Layer:** Redesign and implement the Driver Layer's Finite State Machine (FSM) to be more generic, maintainable, and driven entirely by its configuration. The driver should effectively abstract hardware, respond to intent-based commands from the Governor, and be capable of handling more complex command patterns necessary for future advanced control (e.g., enabling PWM execution). Its behavior should be determined by external commands and its transition rule configuration, without needing direct knowledge of sensor values or complex timing logic internally.
    - **Extensible Governor Layer:** Design the Governor layer to readily support the integration of various control algorithms.
    - **Data Processing & Quality:** Implement a dedicated Data Processing Layer responsible for filtering raw sensor data, validating its integrity, performing sensor calibration routines, handling anomalies (like dropouts or invalid readings), and generating reliable "synthetic" or "virtual" data points. Design for future extensibility towards model-based point generation.
    - **Data Analysis Capability:** Provide tools or a dedicated module/toolkit for interacting with historical data to facilitate analysis, calibration, and model fitting.
    - **Reliability & Error Handling:** Implement robust error handling, status monitoring, and command confirmation mechanisms across all system layers.
    - **Effective Monitoring & Visualization:** Provide comprehensive monitoring of system state and sensor values through Grafana dashboards, fed by data collected via Telegraf and stored in InfluxDB.
    - **Clear Access Control and Command Hierarchy:** Establish and enforce clear access controls and a well-defined command hierarchy between layers (e.g., Governor commands Driver, Driver commands Microcontroller). Define and manage user/developer direct access to system points to ensure stability and predictability.

**3. Overarching Design Principles**

- **Simplicity and Clarity:** Strive for the simplest possible design that meets requirements. Code and configuration should be easy to understand and maintain, especially given the challenges of solo development and ADHD.
- **Single Source of Truth (SSOT):** Configuration is paramount. `system_definition.yaml` and its associated validated configuration files are the definitive description of the system.
- **Buildability:** The entire system, from microcontroller firmware (where possible) to Docker containers, should be buildable from the source code and configurations. The `build.py` script is central to validating and preparing configurations.
- **Modularity:** Components should be well-encapsulated with clearly defined responsibilities and interfaces.
- **Layered Architecture & Progressive Complexity:** Maintain distinct layers (Microcontroller, Driver, Data Processing, Governor) with communication primarily via well-defined interfaces (e.g., MQTT) to decouple components. Layers should exhibit progressive complexity, with the least complexity at the bottom (Microcontroller). Higher layers pass "intent" via commands to lower layers; lower layers are responsible for interpreting and executing that intent according to their configuration, **providing feedback on command execution and resulting state where appropriate.**
- **Interface-Driven Design:** Prioritize the definition of clear, stable interfaces between components and layers *before* detailed implementation. Define components by what they *do* and what information they require/provide.
- **Testability:** Design components and the system in a way that facilitates unit, integration, and (eventually) end-to-end testing.
- **Embrace Structured Testing:** Actively incorporate structured testing practices, including unit and integration tests, to improve code reliability and maintainability. (Well-tested code is also often easier for AI code generation tools to work with).
- **UUID-Based Identification:** All addressable data points and key components in the system will be identified by unique UUIDs, managed through the SSOT.
- **Standardized and Well-Defined Communication Interfaces:** All communication protocols (especially MQTT topics and payload structures) will be clearly defined, documented (e.g., in ADRs), and consistently applied to ensure interoperability and maintainability.
- **Explicit is Better than Implicit:** System behaviors and dependencies should be explicitly defined in configurations or code, rather than relying on implicit conventions.
- **Documentation as a Deliverable:** Treat documentation (like this document, ADRs, architecture docs, READMEs) as a critical part of the project, essential for current clarity and future maintainability.
- **Configuration Validation:** All configuration files must be rigorously validated against defined schemas (e.g., using Pydantic) as part of the build process.
- **Distinction of Point Types:** Clearly distinguish between "physical points," whose values originate from environmental sensors and are reported by microcontrollers, and "virtual points," whose values are generated, synthesized, or aggregated by a specific software component (e.g., Driver, Data Processing Layer), which is considered the source of that point's value.
- **Predictable Loop-Based Execution:** For core control logic, favor predictable timer-based/loop-based execution cycles, with specific decisions on event-driven aspects to be documented (e.g., in ADRs).
- **State and Data Integrity through Verification:** Implement mechanisms at appropriate layers (e.g., Driver, Governor) to verify that system states and critical data points align with intended values or expected conditions. This includes 'readback' validation where actual outputs are compared against setpoints or desired states.
- **Data Timeliness and Freshness:** Strive to ensure data used for control and monitoring is timely and fresh. Implement mechanisms to detect stale or unavailable data. While comprehensive automated handling of all stale data scenarios may be an enhancement for future versions, basic detection and reporting of data staleness are important for V2.

**4. Scope Boundaries (Initial V2 Focus)**

- **In Scope:**
    - Core Control Loops: Focus on implementing robust timer-based and bang-bang control for temperature, humidity, CO2 (implicitly via ventilation), and lighting.
    - SSOT Implementation: Fully realize the `system_definition.yaml` concept and the `build.py` validation for all core components.
    - Driver Refactor: Complete the refactoring of the driver layer to be fully config-driven based on the new SSOT. This includes implementing the necessary FSM states and mechanisms to enable PWM control patterns as commanded by the Governor.
    - Governor Implementation (Basic): Implement the Governor to execute timer and bang-bang logic based on the SSOT.
    - Data Pipeline: Ensure reliable data flow from microcontrollers through to InfluxDB and Grafana. The pipeline must be updated to handle the chosen MQTT payload structure and effectively visualize key data, including discrete states.
    - Data Processing Layer (Basic Implementation): Establish the foundational Data Processing Layer, including capabilities for basic filtering, validation, sensor calibration, and basic detection/reporting of data staleness.
    - Defined Access Permissions: Implement mechanisms to manage and enforce write access permissions for system points according to the defined command hierarchy.
- **Out of Scope for Initial V2 (Potential Future Enhancements):**
    - Advanced PID/MPC control (though the architecture should allow for it).
    - Advanced model-based point generation (e.g., Kalman filtering beyond simple applications) in the Data Processing Layer.
    - Comprehensive automated *handling* strategies for all stale data scenarios (beyond basic detection and reporting).
    - Complex UI beyond Grafana.
    - Automated propagation of config changes to Telegraf (manual updates acceptable initially).
    - Extensive Data Science Toolkit features beyond basic data querying/plotting.
    - Remote access (system remains on internal network).
    - Dedicated Watchdog Layer (though some health/staleness checks may be part of Driver/Data Processing Layer responsibilities).
    - A single, fully automated script to deploy and run *all* heterogeneous components (microcontroller flashing, Docker services, etc.) from scratch (though automation for Python services via Docker Compose is a V2 goal).
