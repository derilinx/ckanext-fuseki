# encoding: utf-8

import logging

import ckan.plugins as p
import ckan.plugins.toolkit as toolkit

import ckanext.fuseki.logic.action as action
import ckanext.fuseki.logic.auth as auth
from ckanext.fuseki import helpers, tasks, views

log = logging.getLogger(__name__)


class JenaPlugin(p.SingletonPlugin):

    p.implements(p.IConfigurer)
    p.implements(p.IActions)
    p.implements(p.IPackageController, inherit=True)
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
    # IPackageController
    # ----------------------

    def after_create(self, context, pkg_dict):
        self._sync_graph(pkg_dict)

    def after_update(self, context, pkg_dict):
        self._sync_graph(pkg_dict)

    def after_delete(self, context, pkg_dict):
        self._sync_graph(pkg_dict, remove=True)

    def _sync_graph(self, pkg_dict, remove=False):
        if not (
            toolkit.config.get("ckanext.fuseki.auto_sync.dataset")
            and p.plugin_loaded("dcat")
        ):
            return

        # anything not public and active must leave the catalog graph
        remove = (
            remove
            or pkg_dict.get("state", "active") != "active"
            or toolkit.asbool(pkg_dict.get("private"))
        )
        toolkit.enqueue_job(
            tasks.sync_catalog_graph,
            [pkg_dict["id"], remove],
            title="fuseki catalog sync {}".format(pkg_dict["id"]),
        )

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
