# INTRA-AS SIMULATION

## Requirements

- Install SCION according to official documentation
    (<https://scion.docs.anapaya.net/en/latest/build/setup.html>)
- Clone SCION-Apps repository (<https://github.com/netsec-ethz/scion-apps>)
    and install/build it according to their README.md

## Installation

- run install_deps.sh

    ```bash
    ./install_deps.sh
    ```

    - this will install routing protocols and other dependencies needed to run the intra-AS simulation

## Usage

- Whole usage can be done with the helper script `scion-intra.sh` in the root directory of this repo.
- First build SCION Proto configuration files:

    ```bash
    ./scion-intra.sh build path-to-intra-AS-config-file path-to-SCION-topo-config-file [other-SCION-topology-flags]
    ```

- Then run the simulation:

    ```bash
    export SCION_APPS_PATH=ath-to-SCION-apps-directory
    ./scion-intra.sh run path-to-intra-AS-config-file
    ```

    - It is also possible to enter the SCION-apps directory directly:

    ```bash
    ./scion-intra.sh run path-to-intra-AS-config-file --apps path-to-SCION-apps-directory
    ```

- Cleanup:
    - only intra AS simulation:

    ```bash
    ./scion-intra.sh clean_intra
    # OR
    ./scion-intra.sh clean
    ```

    - or all:

    ```bash
    ./scion-intra.sh clean_all
    ```
