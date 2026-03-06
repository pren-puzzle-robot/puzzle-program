from .orchestrator import PuzzleOrchestrator


def main() -> None:
    orchestrator = PuzzleOrchestrator()
    result = orchestrator.run_once()
    print(result)


if __name__ == "__main__":
    main()
