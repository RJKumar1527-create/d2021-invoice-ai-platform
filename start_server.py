from __future__ import annotations

import uvicorn

from configuration.settings import settings


def main():
    uvicorn.run(
        "billing_finance_ops_app:application",
        host=settings.app_host,
        port=settings.app_port,
        workers=1,
        access_log=False,
    )


if __name__ == "__main__":
    main()