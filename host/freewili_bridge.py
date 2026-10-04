"""
CrashTest FREE-WILi Bridge

Communicates with the FREE-WILi OG MAIN RP2040 running bench_main.

Verified bench commands:
    iopin <gpio> 0
    iopin <gpio> 1
    iopin <gpio> read

CrashTest SENSOR fault:
    GPIO27 HIGH -> inject fault
    GPIO27 LOW  -> clear fault
"""

import argparse
import sys
import time

import serial
from serial.tools import list_ports


BAUD = 115200

# FREE-WILi OG bench_main USB identity
FREEWILI_VID = 0x093C
FREEWILI_MAIN_PID = 0x2054

PRODUCT_PREFIX = "FWOG main bench"

SENSOR_FAULT_GPIO = 27


class FreeWiliError(Exception):
    pass


def find_freewili_main():
    """
    Automatically locate the FREE-WILi OG MAIN CPU running bench_main.
    """

    exact_matches = []
    name_matches = []

    for port in list_ports.comports():

        product = port.product or ""

        if (
            port.vid == FREEWILI_VID
            and port.pid == FREEWILI_MAIN_PID
        ):
            exact_matches.append(port)

        elif product.startswith(PRODUCT_PREFIX):
            name_matches.append(port)

    matches = exact_matches or name_matches

    if not matches:
        raise FreeWiliError(
            "FREE-WILi MAIN bench firmware not found."
        )

    if len(matches) > 1:
        names = ", ".join(p.device for p in matches)

        raise FreeWiliError(
            f"Multiple FREE-WILi MAIN devices found: {names}"
        )

    return matches[0]


def send_command(command, timeout=2.0):
    """
    Send one newline-terminated command to bench_main.

    Returns:
        port_name, response_lines
    """

    port_info = find_freewili_main()
    port_name = port_info.device

    responses = []

    try:
        with serial.Serial(
            port=port_name,
            baudrate=BAUD,
            timeout=0.1,
            write_timeout=1.0,
        ) as ser:

            # bench.py also communicates with DTR asserted
            ser.dtr = True

            time.sleep(0.15)

            # Remove old heartbeat messages from the receive queue.
            ser.reset_input_buffer()

            payload = command.strip() + "\n"

            ser.write(payload.encode("ascii"))
            ser.flush()

            deadline = time.time() + timeout

            while time.time() < deadline:

                raw = ser.readline()

                if not raw:
                    continue

                line = raw.decode(
                    "utf-8",
                    errors="replace"
                ).strip()

                if not line:
                    continue

                responses.append(line)

                # bench firmware terminates command responses
                # with OK or an error response.
                if line.startswith("OK"):
                    return port_name, responses

                if (
                    line.startswith("ERR")
                    or line.startswith("ERROR")
                ):
                    raise FreeWiliError(
                        f"FREE-WILi returned error: {line}"
                    )

    except serial.SerialException as exc:
        raise FreeWiliError(
            f"Serial communication failed on {port_name}: {exc}"
        ) from exc

    raise FreeWiliError(
        f"No final response from FREE-WILi for command: {command}"
    )


def set_gpio(gpio, level):
    if level not in (0, 1):
        raise ValueError("GPIO level must be 0 or 1.")

    return send_command(
        f"iopin {gpio} {level}"
    )


def read_gpio(gpio):
    return send_command(
        f"iopin {gpio} read"
    )


def inject_sensor_fault():
    """
    HIGH on GPIO27 will later close the external fault switch
    and disrupt the IMU/I2C path.
    """

    return set_gpio(
        SENSOR_FAULT_GPIO,
        1
    )


def clear_sensor_fault():
    return set_gpio(
        SENSOR_FAULT_GPIO,
        0
    )


def print_result(port, lines):
    print(f"FREE-WILi MAIN: {port}")

    for line in lines:
        print(f"  {line}")


def main():

    parser = argparse.ArgumentParser(
        description="CrashTest FREE-WILi OG bridge"
    )

    sub = parser.add_subparsers(
        dest="command",
        required=True
    )

    sub.add_parser(
        "detect",
        help="Detect FREE-WILi MAIN CPU"
    )

    gpio_parser = sub.add_parser(
        "gpio",
        help="Set a FREE-WILi GPIO"
    )

    gpio_parser.add_argument(
        "gpio",
        type=int
    )

    gpio_parser.add_argument(
        "level",
        type=int,
        choices=[0, 1]
    )

    read_parser = sub.add_parser(
        "read",
        help="Read a FREE-WILi GPIO"
    )

    read_parser.add_argument(
        "gpio",
        type=int
    )

    sub.add_parser(
        "sensor-fault",
        help="Inject SENSOR fault using GPIO27"
    )

    sub.add_parser(
        "clear-sensor-fault",
        help="Clear SENSOR fault using GPIO27"
    )

    args = parser.parse_args()

    try:

        if args.command == "detect":

            port = find_freewili_main()

            print("FREE-WILi detected")
            print(f"Port    : {port.device}")
            print(f"Product : {port.product}")
            print(
                f"VID:PID : "
                f"{port.vid:04X}:{port.pid:04X}"
            )

        elif args.command == "gpio":

            port, lines = set_gpio(
                args.gpio,
                args.level
            )

            print_result(port, lines)

        elif args.command == "read":

            port, lines = read_gpio(
                args.gpio
            )

            print_result(port, lines)

        elif args.command == "sensor-fault":

            print(
                f"Injecting SENSOR fault "
                f"using FREE-WILi GPIO{SENSOR_FAULT_GPIO}"
            )

            port, lines = inject_sensor_fault()

            print_result(port, lines)

        elif args.command == "clear-sensor-fault":

            print(
                f"Clearing SENSOR fault "
                f"using FREE-WILi GPIO{SENSOR_FAULT_GPIO}"
            )

            port, lines = clear_sensor_fault()

            print_result(port, lines)

    except FreeWiliError as exc:

        print(
            f"ERROR: {exc}",
            file=sys.stderr
        )

        sys.exit(1)


if __name__ == "__main__":
    main()
