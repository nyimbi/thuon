# main.py

import argparse
from interfaces import cli, web_app, desktop_app, mobile_app  # Import interface modules

def parse_arguments():
    """Parses command line arguments for interface selection.
    Returns:
        argparse.Namespace: Parsed arguments object.
    """
    parser = argparse.ArgumentParser(description='Thuon DeepResearch Platform')
    parser.add_argument('interface', choices=['cli', 'web', 'desktop', 'mobile'], help='Interface to start (cli, web, desktop, mobile)')
    return parser.parse_args()

def main():
    """Main entry point for the Thuon DeepResearch Platform."""
    args = parse_arguments()

    if args.interface == 'cli':
        cli.main_cli()
    elif args.interface == 'web':
        web_app.run_app()
    elif args.interface == 'desktop':
        desktop_app.run_desktop_app()
    elif args.interface == 'mobile':
        mobile_app.run_mobile_app()
    else:
        print('Invalid interface specified.')

if __name__ == '__main__':
    main()
