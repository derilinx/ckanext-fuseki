from unittest import mock

import ckan.plugins as p
import pytest
from ckan.tests import factories, helpers

from ckanext.fuseki import tasks

ENQUEUE = "ckan.plugins.toolkit.enqueue_job"


@pytest.fixture
def dcat_loaded():
    plugin_loaded = p.plugin_loaded
    with mock.patch(
        "ckan.plugins.plugin_loaded",
        side_effect=lambda name: name == "dcat" or plugin_loaded(name),
    ):
        yield


def synced(enqueue, dataset):
    return [
        c.args for c in enqueue.call_args_list if c.args[0] is tasks.sync_catalog_graph
    ]


@pytest.mark.usefixtures("with_plugins", "clean_db", "dcat_loaded")
@pytest.mark.ckan_config("ckanext.fuseki.auto_sync.dataset", "full-catalog")
class TestCatalogSync:
    def test_create_adds_graph(self):
        with mock.patch(ENQUEUE) as enqueue:
            dataset = factories.Dataset()

        assert synced(enqueue, dataset) == [
            (tasks.sync_catalog_graph, [dataset["id"], False])
        ]

    def test_update_adds_graph(self):
        dataset = factories.Dataset()

        with mock.patch(ENQUEUE) as enqueue:
            helpers.call_action("package_patch", id=dataset["id"], title="new title")

        assert synced(enqueue, dataset) == [
            (tasks.sync_catalog_graph, [dataset["id"], False])
        ]

    def test_private_dataset_is_removed(self):
        org = factories.Organization()

        with mock.patch(ENQUEUE) as enqueue:
            dataset = factories.Dataset(owner_org=org["id"], private=True)

        assert synced(enqueue, dataset) == [
            (tasks.sync_catalog_graph, [dataset["id"], True])
        ]

    def test_dataset_made_private_is_removed(self):
        org = factories.Organization()
        dataset = factories.Dataset(owner_org=org["id"])

        with mock.patch(ENQUEUE) as enqueue:
            helpers.call_action("package_patch", id=dataset["id"], private=True)

        assert synced(enqueue, dataset)[-1] == (
            tasks.sync_catalog_graph,
            [dataset["id"], True],
        )

    def test_deleted_dataset_is_removed(self):
        dataset = factories.Dataset()

        with mock.patch(ENQUEUE) as enqueue:
            helpers.call_action("package_delete", id=dataset["id"])

        assert synced(enqueue, dataset)[-1] == (
            tasks.sync_catalog_graph,
            [dataset["id"], True],
        )

    def test_skipped_without_dcat(self):
        with mock.patch(ENQUEUE) as enqueue, mock.patch(
            "ckan.plugins.plugin_loaded", return_value=False
        ):
            factories.Dataset()

        assert not enqueue.called


@pytest.mark.usefixtures("with_plugins", "clean_db", "dcat_loaded")
def test_disabled_without_target_dataset():
    with mock.patch(ENQUEUE) as enqueue:
        factories.Dataset()

    assert not enqueue.called
