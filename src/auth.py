import ee
from pathlib import Path
from typing import Optional


class AuthenticationService:
    """Handles Google Earth Engine authentication."""

    @staticmethod
    def is_initialized() -> bool:
        try:
            ee.Number(1).getInfo()
            return True
        except Exception:
            return False

    @staticmethod
    def authenticate(
        project_id: str = "wildmon-projects",
        service_account: Optional[str] = None,
        key_file: Optional[str | Path] = None,
    ) -> bool:
        """
        Initialize Earth Engine either with user auth (browser) or service account.
        - If service_account and key_file are provided, uses service account.
        - Otherwise uses user auth flow (ee.Authenticate + ee.Initialize).
        """
        try:
            if AuthenticationService.is_initialized():
                print("ℹ️ Earth Engine already initialized")
                return True

            if service_account and key_file:
                credentials = ee.ServiceAccountCredentials(
                    service_account, str(key_file)
                )
                ee.Initialize(credentials=credentials, project=project_id)
            else:
                ee.Authenticate()  # opens browser if needed; if already authed, it’s a no-op
                ee.Initialize(project=project_id)

            # sanity check
            ee.Number(1).getInfo()
            print("✅ Google Earth Engine initialized")
            return True
        except Exception as e:
            print(f"❌ Error initializing Google Earth Engine: {e}")
            print("If you're on a headless/server environment, either run:")
            print("  $ earthengine authenticate")
            print("or use a service account via (service_account, key_file).")
            return False
