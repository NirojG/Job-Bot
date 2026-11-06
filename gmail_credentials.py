"""Use the Windows credential vault for JobFlow's Gmail app password."""

import sys

SERVICE = "Niroj JobFlow Gmail"


def vault():
    if sys.platform != "win32":
        raise ValueError("Saving Gmail credentials is available on Windows.")
    try:
        from keyring.backends.Windows import WinVaultKeyring
    except ImportError as error:
        raise ValueError("Install the updated JobFlow requirements to save Gmail credentials.") from error
    return WinVaultKeyring()


def get_password(sender):
    if not sender:
        return None
    try:
        return vault().get_password(SERVICE, sender)
    except Exception:
        return None


def save_password(sender, password):
    backend = vault()
    try:
        backend.set_password(SERVICE, sender, password)
    except Exception:
        raise ValueError("Windows Credential Manager could not save the app password.") from None


def remove_password(sender):
    backend = vault()
    try:
        if backend.get_password(SERVICE, sender):
            backend.delete_password(SERVICE, sender)
    except Exception:
        raise ValueError("Windows Credential Manager could not remove the app password.") from None
