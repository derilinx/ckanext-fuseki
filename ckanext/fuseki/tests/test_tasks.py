from unittest import mock

import pytest

from ckanext.fuseki import backend, tasks

GRAPH_URL = "http://fuseki:3030/full-catalog"
GRAPH_IRI = "http://ckan/dataset/abc"
CONFIG = {
    "ckanext.fuseki.url": "http://fuseki:3030/",
    "ckanext.fuseki.username": "admin",
    "ckanext.fuseki.password": "admin",
    "ckanext.fuseki.auto_sync.dataset": "full-catalog",
}


@pytest.fixture(autouse=True)
def fuseki_config():
    with mock.patch.object(backend, "config", CONFIG), mock.patch.object(
        tasks, "config", CONFIG
    ), mock.patch.object(tasks, "CKAN_URL", "http://ckan"):
        yield


def test_graph_put_replaces_named_graph():
    with mock.patch("ckanext.fuseki.backend.requests.put") as put:
        backend.graph_put(GRAPH_URL, GRAPH_IRI, "<a> <b> <c> .")

    assert put.call_args.args[0] == GRAPH_URL + "/data"
    assert put.call_args.kwargs["params"] == {"graph": GRAPH_IRI}
    assert put.call_args.kwargs["headers"]["Content-Type"].startswith("text/turtle")
    assert put.call_args.kwargs["auth"] == ("admin", "admin")


def test_graph_remove_ignores_missing_graph():
    with mock.patch("ckanext.fuseki.backend.requests.delete") as delete:
        delete.return_value.status_code = 404
        backend.graph_remove(GRAPH_URL, GRAPH_IRI)

    assert delete.call_args.kwargs["params"] == {"graph": GRAPH_IRI}
    delete.return_value.raise_for_status.assert_not_called()


def test_graph_remove_raises_on_server_error():
    with mock.patch("ckanext.fuseki.backend.requests.delete") as delete:
        delete.return_value.status_code = 500
        backend.graph_remove(GRAPH_URL, GRAPH_IRI)

    delete.return_value.raise_for_status.assert_called_once()


def test_sync_catalog_graph_puts_dcat_ttl():
    get_action = mock.Mock()
    get_action.return_value.return_value = "<a> <b> <c> ."
    with mock.patch.object(tasks, "get_action", get_action), mock.patch.object(
        tasks.backend, "graph_put"
    ) as graph_put:
        tasks.sync_catalog_graph("abc")

    get_action.assert_called_once_with("dcat_dataset_show")
    get_action.return_value.assert_called_once_with(
        {"ignore_auth": True}, {"id": "abc", "format": "turtle"}
    )
    graph_put.assert_called_once_with(GRAPH_URL, GRAPH_IRI, "<a> <b> <c> .")


def test_sync_catalog_graph_removes_graph():
    with mock.patch.object(tasks.backend, "graph_remove") as graph_remove:
        tasks.sync_catalog_graph("abc", remove=True)

    graph_remove.assert_called_once_with(GRAPH_URL, GRAPH_IRI)
