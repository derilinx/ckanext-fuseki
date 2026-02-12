# encoding: utf-8

import logging
from typing import Any, Dict

import ckan.model as model
import ckan.plugins as p
import ckan.plugins.toolkit as toolkit

import ckanext.fuseki.logic.action as action
import ckanext.fuseki.logic.auth as auth
from ckanext.fuseki import helpers, views

log = logging.getLogger(__name__)


class JenaPlugin(p.SingletonPlugin):

    p.implements(p.IConfigurer)
    p.implements(p.IActions)
    p.implements(p.IAuthFunctions)
    p.implements(p.IResourceController, inherit=True)
    p.implements(p.ITemplateHelpers)
    p.implements(p.IBlueprint)

    # ----------------------
    # IConfigurer
    # ----------------------

    def update_config(self, config):
        toolkit.add_template_directory(config, "templates")
        toolkit.add_resource("assets", "fuseki")

    # ----------------------
    # IActions
    # ----------------------

    def get_actions(self):
        return action.get_actions()

    # ----------------------
    # IAuthFunctions
    # ----------------------

    def get_auth_functions(self):
        return auth.get_auth_functions()

    # ----------------------
    # Internal graph update
    # ----------------------

    def _update_graph(self, resource_dict: Dict[str, Any]):
        context = {
            "model": model,
            "ignore_auth": True,
            "defer_commit": True,
        }

        format_ = resource_dict.get("format")
        submit = format_ and format_.lower() in action.DEFAULT_FORMATS

        if not submit:
            return

        try:
            log.debug(
                "Submitting resource %s with format %s to fuseki_update",
                resource_dict["id"],
                format_,
            )

            toolkit.get_action("fuseki_update")(
                context,
                {"id": resource_dict["id"]},
            )

        except toolkit.ValidationError as e:
            log.critical(e)

    # ----------------------
    # ITemplateHelpers
    # ----------------------

    def get_helpers(self):
        return helpers.get_helpers()

    # ----------------------
    # IBlueprint
    # ----------------------

    def get_blueprint(self):
        return views.get_blueprint()
