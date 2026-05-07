workspace "Puzzle Program" "C4 model for the puzzle orchestration software." {
    !identifiers hierarchical

    model {
        operator = person "Operator" "Starts and supervises a puzzle-solving run."

        puzzleProgram = softwareSystem "Puzzle Program" "Python application that captures puzzle images, solves the puzzle layout, maps coordinates, and sends movement commands." {
            orchestrator = container "puzzle_orchestrator" "Composition root and process coordinator. Loads configuration, creates adapters, and executes one puzzle-solving cycle." "Python"
            camera = container "camera_controller" "Captures a puzzle image from the GoPro or returns a configured mock image. Handles ArUco-based image flattening." "Python, OpenCV"
            solver = container "puzzle_solver" "Extracts puzzle pieces from the image and calculates the target placement order and rotations." "Python, OpenCV, Shapely"
            mapper = container "coordinate_mapper" "Converts solver coordinates into machine coordinates using configured scale factors and offsets." "Python"
            microcontroller = container "microcontroller_interface" "Sends pick-and-place movements to the microcontroller through UART, or uses a stub adapter for local runs." "Python, pyserial"
            models = container "puzzle_models" "Shared port protocols and placement data structures." "Python"
            config = container "config.ini" "Runtime configuration for transports, UART, camera, solver, and coordinate mapping." "Configuration" {
                tags "Configuration"
            }
            filesystem = container "Local filesystem" "Stores captured images, flattened images, extracted piece masks, and solver debug output." "Filesystem" {
                tags "Filesystem"
            }

            orchestrator -> config "Reads startup configuration"
            orchestrator -> camera "Captures frame" "CameraPort"
            orchestrator -> solver "Solves puzzle" "PuzzleSolverPort"
            orchestrator -> mapper "Maps placements" "CoordinateMapperPort"
            orchestrator -> microcontroller "Sends machine path" "MicrocontrollerPort"

            camera -> filesystem "Reads mock images and writes flattened captures"
            solver -> filesystem "Writes masks and solved-layout debug images"

            orchestrator -> models "Uses shared ports and placement DTOs"
            camera -> models "Implements CameraPort"
            solver -> models "Returns SolverPlacement"
            mapper -> models "Transforms SolverPlacement to MachinePlacement"
            microcontroller -> models "Consumes MachinePlacement"
        }

        gopro = softwareSystem "GoPro Hero 7 Black" "Camera connected over Wi-Fi."
        tinyK22 = softwareSystem "TinyK22 Microcontroller" "Controller for the physical movement system."
        mechanics = softwareSystem "Mechanics / Actuators" "Physical machine that moves, grips, and places puzzle pieces."
        speaker = softwareSystem "Speaker" "Audio output device used to signal completion and error states."

        operator -> puzzleProgram "Starts a run" "CLI"
        operator -> puzzleProgram.orchestrator "Runs python -m puzzle_orchestrator" "CLI"
        puzzleProgram.camera -> gopro "Sets photo mode, triggers shutter, lists media, and downloads image" "HTTP / Wi-Fi"
        puzzleProgram.microcontroller -> tinyK22 "Sends movement and actuator commands; waits for ACK and DONE" "UART /dev/serial0"
        puzzleProgram.orchestrator -> speaker "Signals completion and error states" "Audio output"
        tinyK22 -> mechanics "Controls motors and gripper"

        production = deploymentEnvironment "Production" {
            raspberryPi = deploymentNode "Raspberry Pi 4 Model B" "Target runtime host." "Linux" {
                python = deploymentNode "Python process" "Single application process." "Python 3.10+" {
                    containerInstance puzzleProgram.orchestrator
                    containerInstance puzzleProgram.camera
                    containerInstance puzzleProgram.solver
                    containerInstance puzzleProgram.mapper
                    containerInstance puzzleProgram.microcontroller
                    containerInstance puzzleProgram.models
                }

                containerInstance puzzleProgram.config
                containerInstance puzzleProgram.filesystem
            }

            goproNode = deploymentNode "GoPro Wi-Fi endpoint" "10.5.5.9" {
                softwareSystemInstance gopro
            }

            controllerNode = deploymentNode "TinyK22 board" "Connected through GPIO14/GPIO15 UART at 57600 baud." {
                softwareSystemInstance tinyK22
            }

            mechanicsNode = deploymentNode "Puzzle mechanics" "Actuators driven by the TinyK22." {
                softwareSystemInstance mechanics
            }

            speakerNode = deploymentNode "Speaker" "Connected audio output for status signalling." {
                softwareSystemInstance speaker
            }
        }
    }

    views {
        systemContext puzzleProgram "SystemContext" {
            include *
            autoLayout lr
            description "Puzzle Program in its hardware and operator context."
        }

        container puzzleProgram "Containers" {
            include *
            description "Main Python packages, configuration, data output, and hardware integrations."
        }

        dynamic puzzleProgram "RuntimeFlow" {
            operator -> puzzleProgram.orchestrator "Starts application"
            puzzleProgram.orchestrator -> puzzleProgram.config "Loads config.ini"
            puzzleProgram.orchestrator -> puzzleProgram.microcontroller "wait_for_start_command()"
            puzzleProgram.orchestrator -> puzzleProgram.camera "capture_frame()"
            puzzleProgram.camera -> gopro "Capture and download image"
            puzzleProgram.orchestrator -> puzzleProgram.solver "solve(frame)"
            puzzleProgram.orchestrator -> puzzleProgram.mapper "map_to_machine(placements)"
            puzzleProgram.orchestrator -> puzzleProgram.microcontroller "send_path(machine_path)"
            puzzleProgram.microcontroller -> tinyK22 "UART pick-and-place sequence"
            tinyK22 -> mechanics "Execute movement"
            description "One puzzle-solving cycle from application start to physical movement."
        }

        deployment puzzleProgram production "ProductionDeployment" {
            include *
            description "Deployment on Raspberry Pi with GoPro, TinyK22, and mechanics."
        }

        styles {
            element "Person" {
                shape person
                background #08427b
                color #ffffff
            }

            element "Software System" {
                background #1168bd
                color #ffffff
            }

            element "Container" {
                background #438dd5
                color #ffffff
            }

            element "Configuration" {
                shape Folder
                background #f5da81
                color #000000
            }

            element "Filesystem" {
                shape cylinder
                background #f5da81
                color #000000
            }
        }

        theme default
    }
}
