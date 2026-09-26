"""The one command that runs the chain.

    python run.py demo
    python run.py read --inbox mail --store raw --out out
    python run.py send --to you@example.com

`demo` fills a folder mailbox with invented invoices and then reads them
back, so the whole thing can be shown without an account anywhere.

`send` posts the same invented invoices to a real address, each under its
issuer's own name, so the chain can be proved against a real server.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import run_pipeline  # noqa: E402
from invoice_generator.build_invoice import fill_mailbox  # noqa: E402
from invoice_generator.mail_delivery import (  # noqa: E402
    MissingAccount, send_invoices,
)
from mailbox_intake.mail_sources import (  # noqa: E402
    ImapMailbox, LocalMailbox,
)
from mailbox_intake.page_text import tesseract_reader  # noqa: E402


def main(argv=None) -> int:
    """Read the arguments, run the chain, print what happened."""
    arguments = build_parser().parse_args(argv)
    if arguments.command == "demo":
        return run_demo(Path(arguments.workdir))
    if arguments.command == "send":
        return send_real(arguments)
    return run_once(arguments)


def build_parser() -> argparse.ArgumentParser:
    """Every way the command can be called."""
    parser = argparse.ArgumentParser(prog="invoice pipeline")
    commands = parser.add_subparsers(dest="command", required=True)

    demo = commands.add_parser(
        "demo", help="invent invoices, mail them, read them back"
    )
    demo.add_argument("--workdir", default="demo")

    once = commands.add_parser("read", help="read a mailbox once")
    once.add_argument("--inbox", default="mail")
    once.add_argument("--store", default="raw")
    once.add_argument("--out", default="out")
    once.add_argument("--imap-host", default="")
    once.add_argument("--imap-user", default="")
    once.add_argument("--imap-folder", default="INBOX")

    post = commands.add_parser(
        "send", help="invent invoices and mail them to a real address"
    )
    post.add_argument("--workdir", default="outbox")
    post.add_argument("--per-layout", type=int, default=1)
    post.add_argument("--to", default="")
    return parser


def run_demo(workdir: Path) -> int:
    """Fill a mailbox with invented invoices, then read it."""
    inbox = workdir / "inbox"
    written = fill_mailbox(inbox, per_layout=2)
    print(f"wrote {len(written.invoices)} invoices into {inbox}")
    print(f"  of which {len(written.scanned)} are scans with no text layer")
    report(
        run_pipeline.run(
            mailbox=LocalMailbox(inbox),
            store=workdir / "raw",
            output=workdir / "out",
            ocr_reader=tesseract_reader,
        )
    )
    return 0


def send_real(arguments) -> int:
    """Invent invoices and mail them to a real address.

    The eight issuers keep their own names on the envelope. The account
    doing the sending comes from the environment, never from an argument,
    so no password reaches the shell history.
    """
    workdir = Path(arguments.workdir)
    filled = fill_mailbox(
        workdir / "drafts",
        per_layout=arguments.per_layout,
        workspace=workdir / "pdf",
    )
    try:
        sent = send_invoices(filled, recipient=arguments.to or None)
    except MissingAccount as missing:
        print(missing)
        return 1
    for delivery in sent:
        print(f"{delivery.invoice_number}  from {delivery.sender}")
    print(f"sent {len(sent)} invoices")
    return 0


def run_once(arguments) -> int:
    """Read a real mailbox, once."""
    report(
        run_pipeline.run(
            mailbox=choose_mailbox(arguments),
            store=Path(arguments.store),
            output=Path(arguments.out),
            ocr_reader=tesseract_reader,
        )
    )
    return 0


def choose_mailbox(arguments):
    """A folder of mail files, or a real server.

    The password is asked for, never read from an argument, so it does not
    end up in the shell history.
    """
    if not arguments.imap_host:
        return LocalMailbox(Path(arguments.inbox))
    import getpass

    return ImapMailbox(
        host=arguments.imap_host,
        user=arguments.imap_user,
        password=getpass.getpass("IMAP password: "),
        folder=arguments.imap_folder,
    )


def report(summary) -> None:
    """Say what the run did, in the order a reader cares about."""
    print(f"stored        {summary.stored}")
    print(f"read as text  {summary.read_as_text}")
    print(f"read by model {summary.read_by_model}")
    print(f"unrecognised  {summary.unrecognised}")
    print(f"unreadable    {summary.unreadable}")
    print(f"flagged       {summary.flagged}")
    print(f"lines    -> {summary.lines_csv}")
    print(f"findings -> {summary.findings_csv}")
    for problem in summary.problems:
        print(f"  could not read {problem}")


if __name__ == "__main__":
    sys.exit(main())
