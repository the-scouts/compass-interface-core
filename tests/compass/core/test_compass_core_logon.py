import datetime

import pydantic
import pytest
import requests

from compass.core import logon
from compass.core.errors import CompassError
import compass.core.schemas.logon as schema
from compass.core.settings import Settings
from compass.core.util.client import Client

from tests.util.fake_compass import asp_net_id

base_domain = "127.0.0.1"
base_url = "http://127.0.0.1:4200"


class TestLogon:
    def test_login_get_cookie(self, server):
        # Given
        Settings.base_url = base_url

        # When
        client = logon.create_session()

        # Then
        assert isinstance(client, requests.Session)
        assert isinstance(client, Client)
        assert client.cookies["ASP.NET_SessionId"] == asp_net_id

    def test_login_no_cookie(self, server):
        # Given
        Settings.base_url = f"{base_url}/_testing/no-cookie"

        # Then
        with pytest.raises(CompassError, match="Could not create a session with Compass"):
            # When
            logon.create_session()

    def test_login_post_credentials(self, server, monkeypatch: pytest.MonkeyPatch):
        # Given
        Settings.base_url = base_url
        client = Client()
        client.cookies.set("ASP.NET_SessionId", asp_net_id, domain=base_domain)

        # When
        monkeypatch.setattr(logon, "check_login", lambda _client: (schema.CompassProps(), {}))
        response, _props, _roles = logon.logon_remote(client, ("username", "password"))

        # Then
        expected_response = b"<head><title>Compass - System Startup</title><link rel='shortcut icon' type='image/vnd.microsoft.icon' href='https://compass.scouts.org.uk/Images/core/ico_compass.ico' sizes='16x16 24x24 32x32 48x48'></head><body onload='window.location.href=\"https://compass.scouts.org.uk/ScoutsPortal.aspx\"'></body>"  # NoQA: E501
        assert client.cookies["ASP.NET_SessionId"] == asp_net_id  # always need cookie
        assert response.content == expected_response

    def test_login_post_incorrect_credentials(self, server, monkeypatch: pytest.MonkeyPatch):
        # Given
        Settings.base_url = base_url
        client = Client()
        client.cookies.set("ASP.NET_SessionId", asp_net_id, domain=base_domain)

        # When
        monkeypatch.setattr(logon, "check_login", lambda _client: (schema.CompassProps(), {}))
        response, _props, _roles = logon.logon_remote(client, ("wrong", "credentials"))

        # Then
        expected_response = b"<head><title>Compass - Failed Login</title><link rel='shortcut icon' type='image/vnd.microsoft.icon' href='https://compass.scouts.org.uk/Images/core/ico_compass.ico' sizes='16x16 24x24 32x32 48x48'></head><body onload='window.location.href=\"\"'></body>"  # NoQA: E501
        assert client.cookies["ASP.NET_SessionId"] == asp_net_id  # always need cookie
        assert response.content == expected_response

    def test_login_check_login(self, server):
        # Given
        Settings.base_url = base_url
        client = Client()
        client.cookies.set("ASP.NET_SessionId", asp_net_id, domain=base_domain)

        # When
        props, roles = logon.check_login(client)

        # Then
        expected_props = schema.CompassProps(
            nav=schema.CompassPropsNav(action="None", start_no=-1, start_page=3),
            page=schema.CompassPropsPage(
                use_cn=10000000,
                hide_badges=True,
                croc="OK",
                hide_nominations=True,
                can_delete_ogl_hrs=False,
                fold_name="MP_",
            ),
            crud=schema.CompassPropsCRUD(mdis="R", roles="R", pemd="R", mmmd="R", mvid="R", perm="R", trn="CRD"),
            user=schema.CompassPropsUser(is_me=True),
            master=schema.CompassPropsMaster(
                sso=schema.CompassPropsMasterSSO(on=10000001),
                user=schema.CompassPropsMasterUser(
                    cn=10000000,
                    mrn=9000000,
                    on=10000001,
                    lvl="ORG",
                    jk="9b65d68f4aca0138b5bae4492e7cdfae220a834e3e69731d996be1ddbb496d32fd29497d4f9729525c9fbc77666bb520ea214c0802ea22b958e6ae525224fd15",  # NoQA: E501
                ),
                const=schema.CompassPropsMasterConst(wales=10000007, scotland=10000005, over_seas=10000002, hq=10000001),
                sys=schema.CompassPropsMasterSys(
                    session_id="d6c76537-1b6c-3910-c3d4-d21d4e6453a6",
                    safe_json=True,
                    web_path=pydantic.HttpUrl(
                        "https://compass.scouts.org.uk/JSon.svc/",
                        scheme="https",
                        host="compass.scouts.org.uk",
                        tld="uk",
                        host_type="domain",
                        path="/JSon.svc/",
                    ),
                    text_size=1,
                    timout=1729000,
                    rest=True,
                    hard_time=datetime.time(20, 18, 28),
                    hard_expiry="6 hours",
                    timeout_extension=10,
                    ping=300000,
                ),
            ),
            const=schema.CompassPropsConst(sys=schema.CompassPropsConstSys(sto=5, sto_ask=0)),
        )

        expected_roles = {
            9000000: ("Regional Administrator", "Wessex"),
            6857721: ("TSA Council Member - Nominated Member (18-24)", "The Scout Association"),
        }

        assert client.cookies["ASP.NET_SessionId"] == asp_net_id  # always need cookie
        assert props == expected_props
        assert roles == expected_roles

    def test_login_from_session_props(self, server):
        # Given
        Settings.base_url = base_url
        user_props = {
            "cn": 10000000,
            "mrn": 9000000,
            "on": 10000001,
            "lvl": "ORG",
            "jk": "9b65d68f4aca0138b5bae4492e7cdfae220a834e3e69731d996be1ddbb496d32fd29497d4f9729525c9fbc77666bb520ea214c0802ea22b958e6ae525224fd15",  # NoQA: E501
        }
        session_id = "d6c76537-1b6c-3910-c3d4-d21d4e6453a6"
        current_role = "Role", "Place"

        # When
        session = logon.Logon.from_session(asp_net_id, user_props, session_id, current_role)

        # Then
        assert session._client.cookies["ASP.NET_SessionId"] == asp_net_id
        assert session._asp_net_id == asp_net_id

        assert session._session_id == session_id
        assert session._client.headers["SID"] == session_id

        assert session._client.headers["Authorization"] == f'{user_props["cn"]}~{user_props["mrn"]}'

        assert session.current_role == current_role
        assert session.membership_number == user_props["cn"]
        assert session.role_number == user_props["mrn"]
        assert session._jk == user_props["jk"]
