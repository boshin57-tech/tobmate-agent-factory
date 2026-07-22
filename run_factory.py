from tobmate_agents.factory import run_chapter
import argparse
import asyncio

def main() -> None:
    parser = argparse.ArgumentParser(description="TOBMATE Multi-Agent Factory")
    parser.add_argument("--chapter", default="3O", help="Example: 3O")
    args = parser.parse_args()
    output = asyncio.run(run_chapter(args.chapter))
    print(output)

if __name__ == "__main__":
    main()
