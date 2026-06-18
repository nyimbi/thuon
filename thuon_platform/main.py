# main.py

import argparse
from interfaces import cli, web_app, desktop_app, mobile_app  # Import interface modules

def parse_arguments():
    """Parses command line arguments for interface selection.
    Returns:
        argparse.Namespace: Parsed arguments object.
    """
    parser = argparse.ArgumentParser(description='Thuon DeepResearch Platform')
    parser.add_argument('interface', choices=['cli', 'web', 'desktop', 'mobile', 'mcp'], help='Interface to start (cli, web, desktop, mobile, mcp)')
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
    elif args.interface == 'mcp':
        import sys
        sys.path.insert(0, __file__.replace('/main.py', ''))
        from core.mcp_server import run_mcp_stdio
        from interfaces.web_app import create_app
        app = create_app()
        with app.app_context():
            run_mcp_stdio(app.instance_factory)
    else:
        print('Invalid interface specified.')

if __name__ == '__main__':
    main()
