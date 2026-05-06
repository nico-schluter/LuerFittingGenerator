from .luerFitting import entry as luerFitting

commands = [
    luerFitting,
]


def start():
    for command in commands:
        command.start()


def stop():
    for command in commands:
        command.stop()
