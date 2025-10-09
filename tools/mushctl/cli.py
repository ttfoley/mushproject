from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from shared_libs.points_cli_core.registry_loader import load_registry
from shared_libs.points_cli_core.search import resolve_by_uuid_or_name
from shared_libs.points_cli_core.validation import (
	ValidationError,
	check_access,
	check_acl,
	coerce_and_validate_value,
)
from shared_libs.points_cli_core.payload import build_payload
from shared_libs.points_cli_core.mqtt_client import publish_json


app = typer.Typer(help="mushctl - SSOT-aware CLI for command points")


@app.callback()
def common(
	registry_path: Optional[Path] = typer.Option(
		None,
		"--registry",
		help="Path to global_points_registry.json (defaults to artifacts/points_registry/global_points_registry.json)",
	),
):
	"""Common options placeholder for future use."""
	# Typer requires a callback signature for global options; no-op for now
	return


points_app = typer.Typer(help="Points-related commands")
app.add_typer(points_app, name="points")


@points_app.command("list")
def points_list(
	match: Optional[str] = typer.Option(None, "--match", help="Substring match on point name"),
	only_commands: bool = typer.Option(True, "--commands/--all", help="Limit to command points"),
	limit: int = typer.Option(50, "--limit", help="Max results to show"),
):
	reg = load_registry()
	points = list(reg.all_points())
	if only_commands:
		points = [p for p in points if p.function_grouping == "command"]
	if match:
		mk = match.lower()
		points = [p for p in points if mk in p.name.lower()]
	for p in points[: max(0, limit)]:
		writable = ",".join(p.writable_by or [])
		print(f"{p.name} | uuid={p.uuid} | topic={p.mqtt_topic} | type={p.value_type} | writable_by=[{writable}]")


@app.command("write")
def write_command(
	uuid: Optional[str] = typer.Option(None, "--uuid", help="Target point UUID"),
	name: Optional[str] = typer.Option(None, "--name", help="Name substring to select point"),
	value: str = typer.Option(..., "--value", help="Value to write (string or number)"),
	as_role: str = typer.Option(..., "--as", help="Identity/role (e.g., Manual_HOA, superuser)"),
	trace: bool = typer.Option(False, "--trace/--no-trace", help="Include source and command_id in payload"),
	force: bool = typer.Option(False, "--force", help="Allow superuser to bypass ACL"),
	dry_run: bool = typer.Option(False, "--dry-run", help="Validate and print, but do not publish"),
	print_json: bool = typer.Option(False, "--print-json", help="Print the JSON payload"),
	strict_embedded: bool = typer.Option(False, "--strict-embedded", help="Send minimal payload for embedded targets"),
):
	reg = load_registry()
	matches = resolve_by_uuid_or_name(reg, uuid=uuid, name_substring=name)
	if not matches:
		typer.secho("No point matched.", fg=typer.colors.RED)
		raise typer.Exit(code=1)
	point = matches[0]
	try:
		check_access(point)
		check_acl(point, as_role, superuser=(as_role == "superuser"), force=force)
		coerced = coerce_and_validate_value(point, value)
	except ValidationError as e:
		typer.secho(str(e), fg=typer.colors.RED)
		raise typer.Exit(code=2)
	payload = build_payload(point, coerced, role=as_role, trace=trace, strict_embedded=strict_embedded)
	if dry_run or print_json:
		prefix = "FORCE " if (as_role == "superuser" and force) else ""
		print(f"Topic: {point.mqtt_topic}")
		print(f"{prefix}Payload:")
		print(json.dumps(payload, indent=2))
	if not dry_run:
		publish_json(point.mqtt_topic, payload, role=as_role)
		if as_role == "superuser" and force:
			typer.secho("FORCE WRITE: superuser bypassed ACL", fg=typer.colors.YELLOW)


@app.command("shell")
def shell() -> None:
	"""Interactive session for listing, selecting and writing points."""
	reg = load_registry()
	current_role = "Manual_HOA"
	force = False
	trace = False
	strict_embedded = False
	dry_run = False
	print_json = False
	current_point = None
	last_matches = []

	def _print_help() -> None:
		print("Commands:")
		print("  help                     Show this help")
		print("  list [substr]            List command points (optionally filter by name substring)")
		print("  use <uuid|substr|#N>     Select a point by uuid, substring, or last list index")
		print("  show                     Show current selection and settings")
		print("  role <name>              Set identity/role (e.g., Manual_HOA, superuser)")
		print("  force on|off             Toggle superuser ACL bypass (effective only with role superuser)")
		print("  trace on|off             Toggle including source/command_id in payload")
		print("  strict on|off            Toggle strict-embedded minimal payload")
		print("  dry on|off               Toggle dry-run (no publish)")
		print("  print on|off             Toggle printing JSON payload")
		print("  write <value>            Publish write for current point")
		print("  exit|quit                Leave the shell")

	_print_help()
	while True:
		try:
			line = input("mushctl> ").strip()
		except (EOFError, KeyboardInterrupt):
			print()
			break
		if not line:
			continue
		parts = line.split()
		cmd = parts[0].lower()
		args = parts[1:]

		if cmd in {"exit", "quit"}:
			break
		if cmd == "help":
			_print_help()
			continue
		if cmd == "list":
			match = args[0] if args else None
			points = [p for p in reg.all_points() if p.function_grouping == "command"]
			if match:
				mk = match.lower()
				points = [p for p in points if mk in p.name.lower()]
			last_matches = points
			for idx, p in enumerate(points[:200]):
				writable = ",".join(p.writable_by or [])
				print(f"#{idx}: {p.name} | uuid={p.uuid} | topic={p.mqtt_topic} | type={p.value_type} | writable_by=[{writable}]")
			continue
		if cmd == "use":
			if not args:
				print("usage: use <uuid|substr|#N>")
				continue
			arg = args[0]
			# Support index selection with or without '#'
			if (arg.startswith("#") and arg[1:].isdigit()) or arg.isdigit():
				idx = int(arg[1:]) if arg.startswith("#") else int(arg)
				if 0 <= idx < len(last_matches):
					current_point = last_matches[idx]
					print(f"Selected: {current_point.name} ({current_point.uuid})")
					continue
				else:
					print("index out of range")
					continue
			matches = resolve_by_uuid_or_name(reg, uuid=arg, name_substring=arg)
			if not matches:
				print("No matches")
				continue
			if len(matches) > 1:
				last_matches = matches
				for idx, p in enumerate(matches):
					print(f"#{idx}: {p.name} | uuid={p.uuid}")
				print("Multiple matches. Pick with: use #N")
				continue
			current_point = matches[0]
			print(f"Selected: {current_point.name} ({current_point.uuid})")
			continue
		if cmd == "show":
			print(f"role={current_role} force={force} trace={trace} strict={strict_embedded} dry={dry_run} print={print_json}")
			if current_point:
				writable = ",".join(current_point.writable_by or [])
				print(f"point: {current_point.name} | uuid={current_point.uuid} | topic={current_point.mqtt_topic} | type={current_point.value_type} | writable_by=[{writable}]")
			else:
				print("point: <none>")
			continue
		if cmd == "role" and args:
			current_role = args[0]
			print(f"role set to {current_role}")
			continue
		if cmd == "force" and args:
			force = args[0].lower() in {"on", "true", "1", "yes"}
			print(f"force={force}")
			continue
		if cmd == "trace" and args:
			trace = args[0].lower() in {"on", "true", "1", "yes"}
			print(f"trace={trace}")
			continue
		if cmd == "strict" and args:
			strict_embedded = args[0].lower() in {"on", "true", "1", "yes"}
			print(f"strict={strict_embedded}")
			continue
		if cmd == "dry" and args:
			dry_run = args[0].lower() in {"on", "true", "1", "yes"}
			print(f"dry={dry_run}")
			continue
		if cmd == "print" and args:
			print_json = args[0].lower() in {"on", "true", "1", "yes"}
			print(f"print={print_json}")
			continue
		if cmd == "write":
			if not current_point:
				print("No point selected. Use 'use' first.")
				continue
			if not args:
				print("usage: write <value>")
				continue
			val = args[0]
			try:
				check_access(current_point)
				check_acl(current_point, current_role, superuser=(current_role == "superuser"), force=force)
				coerced = coerce_and_validate_value(current_point, val)
			except ValidationError as e:
				print(str(e))
				continue
			payload = build_payload(current_point, coerced, role=current_role, trace=trace, strict_embedded=strict_embedded)
			if print_json or dry_run:
				prefix = "FORCE " if (current_role == "superuser" and force) else ""
				print(f"Topic: {current_point.mqtt_topic}")
				print(f"{prefix}Payload:")
				print(json.dumps(payload, indent=2))
			if not dry_run:
				publish_json(current_point.mqtt_topic, payload, role=current_role)
				if current_role == "superuser" and force:
					print("FORCE WRITE: superuser bypassed ACL")
			continue
		print("Unknown command. Type 'help' for usage.")

def main() -> None:
	app()


if __name__ == "__main__":
	main()


