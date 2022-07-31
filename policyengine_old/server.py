"""
The PolicyEngine server logic (Flask-based).
"""
import os
from pathlib import Path
from typing import Tuple, Type
from flask import Flask, request, send_from_directory
from flask_cors import CORS
from time import time
from policyengine_old.utils.general import (
    get_cached_result,
    after_request_func,
    set_cached_result,
)
from policyengine_old.countries import UK, US, PolicyEngineCountry
from policyengine_old import VERSION
from policyengine_old.utils.social_card import add_social_card_metadata


class PolicyEngine:
    version: str = VERSION
    cache_bucket_name: str = "uk-policy-engine.appspot.com"
    countries: Tuple[Type[PolicyEngineCountry]] = (UK, US)

    def _init_countries(self):
        self.countries = list(map(lambda country: country(), self.countries))

    def _init_forwarding(self):
        def static_site(e):
            with open(
                str(Path(__file__).parent / "static" / "index.html")
            ) as f:
                text = f.read()
                modified = add_social_card_metadata(request.path, text)
            with open(
                str(Path(__file__).parent / "static" / "index_mod.html"), "w"
            ) as f:
                f.write(modified)
            response = send_from_directory(
                str(Path(__file__).parent / "static"), "index_mod.html"
            )
            return response

        self.static_site = self.app.errorhandler(404)(static_site)

        def pass_params_and_cache(fn):
            def new_fn(*args, **kwargs):
                params = {**request.args, **(request.json or {})}
                cached_result = None
                cache = (
                    self.cache
                    if not hasattr(fn, "_exclude_from_cache")
                    else None
                )
                if cache is not None:
                    cached_result = get_cached_result(
                        params, fn.__name__, self.version, self.cache
                    )
                if cached_result is not None:
                    return cached_result
                else:
                    result = fn(*args, params=params, **kwargs)
                    if cache is not None:
                        set_cached_result(
                            params,
                            fn.__name__,
                            self.version,
                            self.cache,
                            result,
                        )
                    return result

            new_fn.__name__ = (
                "cached_" if not hasattr(fn, "_exclude_from_cache") else ""
            ) + fn.__name__
            return new_fn

        for country in self.countries:
            for route, handler in country.api_endpoints.items():
                fn = handler
                for decorator in (
                    pass_params_and_cache,
                    self.app.route(
                        f"/{country.name}/api/{route.replace('_', '-')}",
                        methods=["GET", "POST"],
                        endpoint=f"{country.name}_{route}",
                    ),
                ):
                    fn = decorator(fn)
                    setattr(self, fn.__name__, fn)

        self.after_request_func = self.app.after_request(after_request_func)

    def _init_flask(self):
        self.app = Flask(
            type(self).__name__,
            static_url_path="",
            static_folder=str((Path(__file__).parent / "static").absolute()),
        )
        CORS(self.app)

    @property
    def debug_mode(self):
        return bool(os.environ.get("POLICYENGINE_DEBUG"))

    def _init_cache(self):
        if self.cache_bucket_name is not None and not self.debug_mode:
            from google.cloud import storage

            self.cache = storage.Client().get_bucket(self.cache_bucket_name)
        else:
            self.cache = None

    def __init__(self):
        self._init_flask()
        self.app.logger.info("Initialising server.")
        self._init_countries()
        self._init_cache()
        self._init_forwarding()
        self.app.logger.info("Initialisation complete.")


app = PolicyEngine().app
