import argparse
import urllib.parse

def main():
    parser = argparse.ArgumentParser(description="Generate a Google Calendar event link")
    parser.add_argument("--title", required=True, help="Event title")
    parser.add_argument("--description", default="", help="Event description")
    parser.add_argument("--start", default="", help="Start date/time (YYYYMMDDTHHMMSSZ or YYYYMMDD)")
    parser.add_argument("--end", default="", help="End date/time (YYYYMMDDTHHMMSSZ or YYYYMMDD)")
    
    args = parser.parse_args()
    
    params = {
        'action': 'TEMPLATE',
        'text': args.title
    }
    if args.description:
        params['details'] = args.description
    if args.start and args.end:
        params['dates'] = f"{args.start}/{args.end}"
    elif args.start:
        params['dates'] = f"{args.start}/{args.start}"
        
    url = f"https://calendar.google.com/calendar/r/eventedit?{urllib.parse.urlencode(params)}"
    print(f"[{args.title}]({url})")

if __name__ == "__main__":
    main()
