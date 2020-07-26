from typing import Tuple

import requests
from lxml import html

from src.utility import CompassSettings


class CompassLogon:
    def __init__(self, credentials: list, role_to_use: str):
        self._member_role_number = 0
        self.compass_dict = {}

        self.credentials: list = credentials
        self.role_to_use: str = role_to_use

        self.session: requests.sessions.Session = self.do_logon(credentials, role_to_use)

    @property
    def mrn(self) -> int:
        return self.compass_dict["Master.User.MRN"]  # Member Role Number

    @property
    def cn(self) -> int:
        return self.compass_dict["Master.User.CN"]  # Contact Number

    @property
    def jk(self) -> int:
        return self.compass_dict["Master.User.JK"]  # ???? Key?

    def get(self, url, **kwargs):
        CompassSettings.total_requests += 1
        return self.session.get(url, **kwargs)

    def post(self, url, **kwargs):
        CompassSettings.total_requests += 1
        data = kwargs.pop("data", None)
        json_ = kwargs.pop("json", None)
        return self.session.post(url, data=data, json=json_, **kwargs)

    def do_logon(self, credentials: list = None, role_to_use: str = None) -> requests.sessions.Session:
        """Log in to Compass, change role and confirm success."""
        session = self.create_session()

        self._logon(credentials)
        compass_dict, roles_dict = self.confirm_success_and_update(session, check_url=True)

        if role_to_use:
            self.change_role(session, role_to_use, roles_dict)
        else:
            print("not changing role")

        return session

    def create_session(self) -> requests.sessions.Session:
        # Create a session and get ASP.Net Session ID cookie from the compass server.
        session = requests.session()

        session.head(f"{CompassSettings.base_url}/", verify=False)  # use .head() as only headers needed to grab session cookie
        CompassSettings.total_requests += 1

        if not session.cookies:
            raise Exception("No cookie found, terminating.")

        self.session = session
        return session

    def _logon(self, auth: list) -> requests.models.Response:
        # Referer is genuinely needed otherwise login doesn't work
        headers = {'Referer': f'{CompassSettings.base_url}/login/User/Login'}

        username, password = auth
        credentials = {
            'EM': f"{username}",  # assume email?
            'PW': f"{password}",  # password
            'ON': f'{CompassSettings.org_number}'  # organisation number
        }

        # log in
        print("Logging in")
        response = self.post(f'{CompassSettings.base_url}/Login.ashx', headers=headers, data=credentials, verify=False)
        return response

    def _change_role(self, new_role: str, roles_dict: dict) -> int:
        # Get role number from roles dictionary
        member_role_number = roles_dict[new_role]

        # Change role to the specified role
        self.post(f"{CompassSettings.base_url}/API/ChangeRole", json={"MRN": member_role_number}, verify=False)

        return member_role_number

    def change_role(self, session: requests.sessions.Session, new_role: str, roles_dict: dict):
        print("Changing role")
        new_role = new_role.strip()

        member_role_number = self._change_role(new_role, roles_dict)
        self.confirm_success_and_update(session, check_role_number=member_role_number)

        print(f"Role changed to {new_role}")

    def create_compass_dict(self, form_tree: html.FormElement) -> dict:
        compass_dict = {}
        compass_vars = form_tree.fields["ctl00$_POST_CTRL"]
        for pair in compass_vars.split('~'):
            key, value, *_ = pair.split('#')
            compass_dict[key] = value

        self.compass_dict = compass_dict
        return compass_dict

    @staticmethod
    def create_roles_dict(form_tree: html.FormElement):
        """Dict comprehension to generate role name: role number mapping"""
        roles_selector: html.SelectElement = form_tree.inputs['ctl00$UserTitleMenu$cboUCRoles']  # get roles from compass page (list of option tags)
        return {role.text.strip(): role.get("value").strip() for role in roles_selector.iter("option")}

    @staticmethod
    def get_selected_role_number(form_tree: html.FormElement):
        return form_tree.inputs['ctl00$UserTitleMenu$cboUCRoles'].value

    def confirm_success_and_update(self, session: requests.sessions.Session, check_url: bool = False, check_role_number: int = 0) -> Tuple[dict, dict]:
        portal_url = f"{CompassSettings.base_url}/ScoutsPortal.aspx"
        response = self.get(portal_url, verify=False)

        # # Response body is login page for failure (~8Kb), but success is a 300 byte page.
        # if int(post_response.headers.get("content-length", 901)) > 900:
        #     raise Exception("Login has failed")
        if check_url and response.url != portal_url:
            raise Exception("Login has failed")

        form: html.FormElement = html.fromstring(response.content).forms[0]

        if check_role_number:
            print("Confirming role has been changed")
            # Check that the role has been changed to the desired role. If not, raise exception.
            if self.get_selected_role_number(form) != check_role_number:
                raise Exception("Role failed to update in Compass")

        compass_dict = self.create_compass_dict(form)
        roles_dict = self.create_roles_dict(form)

        # Set auth headers for new role
        auth_headers = {
            "Authorization": f'{self.cn}~{self.mrn}',
            "SID": compass_dict["Master.Sys.SessionID"]  # Session ID
        }
        session.headers.update(auth_headers)

        if check_role_number and check_role_number != self.mrn:
            raise Exception("Compass Authentication failed to update")

        # TODO is this get role bit needed given that we change the role?
        role_name = {v: k for k,v in roles_dict.items()}.get(self.mrn)
        print(f"All good! Using Role: {role_name}")

        return compass_dict, roles_dict