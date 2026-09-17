from utils import generate_calendar_url

def main():
    parser = argparse.ArgumentParser(description="Generate a Google Calendar event link")
    parser.add_argument("--title", required=True, help="Event title")
    parser.add_argument("--description", default="", help="Event description")
    parser.add_argument("--start", default="", help="Start date/time (YYYYMMDDTHHMMSSZ or YYYYMMDD)")
    parser.add_argument("--end", default="", help="End date/time (YYYYMMDDTHHMMSSZ or YYYYMMDD)")
    
    args = parser.parse_args()
    url = generate_calendar_url(args.title, args.description, args.start, args.end)
    print(f"[{args.title}]({url})")

if __name__ == "__main__":
    main()
