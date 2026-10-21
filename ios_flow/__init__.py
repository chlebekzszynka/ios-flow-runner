"""iOS Flow Runner — sterowanie aplikacjami iOS przez Appium według pliku JSON."""

__version__ = "1.0"
__codename__ = "Pierwsza Kromka"


def version_banner() -> str:
    """Tekst wypisywany przez ``--version``."""
    return (
        f'iOS Flow Runner {__version__} "{__codename__}"\n'
        "Non-vegetarian build, sponsored by chlebek z szynką"
    )
