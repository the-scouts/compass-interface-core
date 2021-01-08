import contextlib
import datetime
import re
import time
from typing import Literal, get_args, Union, Optional

import requests
from dateutil.parser import parse
from dateutil.parser import parserinfo as _parserinfo
from lxml import html

from compass.interface_base import CompassInterfaceBase
from compass.settings import Settings
from compass.utility import cast

MEMBER_PROFILE_TAB_TYPES = Literal["Personal", "Roles", "Permits", "Training", "Awards", "Emergency", "Comms", "Visibility", "Disclosures"]


def _parse(timestr: str, parserinfo: Optional[_parserinfo] = None, **kwargs) -> Optional[datetime.datetime]:
    return parse(timestr, parserinfo, **kwargs) if timestr else None


class CompassPeopleScraper(CompassInterfaceBase):
    """

    Class directly interfaces with Compass operations to extract member data.

    Compass's MemberProfile.aspx has 13 tabs:
     1. Personal Details (No Key)
     2. Your Children (Page=CHILD)
     3. Roles (Page=ROLES)
     4. Permits (Page=PERMITS)
     5. Training (Page=TRAINING)
     6. Awards (Page=AWARDS)
     7. Youth Badges/Awards (Page=BADGES)
     8. Event Invitations (Page=EVENTS)
     9. Emergency Details (Page=EMERGENCY)
     10. Communications (Page=COMMS)
     11. Visibility (Page=VISIBILITY)
     12. Disclosures (Page=DISCLOSURES)
     13. Parents/Guardians (Page=PARENT)

    Of these, tabs 2, 7, 8, 13 are disabled functionality.
    Tab 11 (Visibility) is only shown on the members' own profile.

    For member-adjdacent operations there are additional endpoints:
     - /Popups/Profile/AssignNewRole.aspx
     - /Popups/Maint/NewPermit.aspx
     - /Popups/Profile/EditProfile.aspx

    Currently we only use one of these endpoints (AssignNewRole), as all
    other data we need can be found from the MemberProfile tabs.

    All functions in the class output native types.
    """
    def __init__(self, session: requests.Session):
        """CompassPeopleScraper constructor.

        takes an initialised Session object from CompassLogon
        """
        super().__init__(session)

    def _get_member_profile_tab(self, membership_num: int, profile_tab: MEMBER_PROFILE_TAB_TYPES) -> bytes:
        """Returns data from a given tab in MemberProfile for a given member.

        Args:
            membership_num: Membership Number to use
            profile_tab: Tab requested from Compass

        Returns:
            A dict with content and encoding, e.g.:

            {"content": b"...", "encoding": "utf-8"}

            Both keys will always be present.

        Raises:
            ValueError: The given profile_tab value is illegal

        Todo:
            Other possible exceptions? i.e. from Requests
        """
        profile_tab = profile_tab.upper()
        tabs = tuple(tab.upper() for tab in get_args(MEMBER_PROFILE_TAB_TYPES))
        url = f"{Settings.base_url}/MemberProfile.aspx?CN={membership_num}"
        if profile_tab == "PERSONAL":  # Personal tab has no key so is a special case
            response = self._get(url)
        elif profile_tab in tabs:
            url += f"&Page={profile_tab}&TAB"
            response = self._get(url)
        else:
            raise ValueError(f"Specified member profile tab {profile_tab} is invalid. Allowed values are {tabs}")

        return response.content

    def get_personal_tab(self, membership_num: int) -> dict[str, Union[int, str, datetime.datetime]]:
        """Returns data from Personal Details tab for a given member.

        Args:
            membership_num: Membership Number to use

        Returns:
            A dict mapping keys to the corresponding data from the personal
            data tab.

            For example:
            {'membership_number': ...,
             'forenames': '...',
             'surname': '...',
             'main_phone': '...',
             'main_email': '...',
             'name': '...',
             'known_as': '...',
             'join_date': datetime.datetime(...),
             'sex': '...',
             'birth_date': datetime.datetime(...),
             'nationality': '...',
             'ethnicity': '...',
             'religion': '...',
             'occupation': '...',
             'address': '...'}

            Keys will be present only if valid data could be extracted and
            parsed from Compass.

        Raises:
            PermissionError:
                Access to the member is not given by the current authentication

        Todo:
            Other possible exceptions? i.e. from Requests
        """
        response = self._get_member_profile_tab(membership_num, "Personal")

        tree = html.fromstring(response)

        if tree.forms[0].action == "./ScoutsPortal.aspx?Invalid=AccessCN":
            raise PermissionError(f"You do not have permission to the details of {membership_num}")

        details = dict()

        # ### Extractors
        # ## Core:

        details["membership_number"] = membership_num

        # Name(s)
        names = tree.xpath("//title//text()")[0].strip().split(" ")[3:]
        details["forenames"] = names[0]
        details["surname"] = " ".join(names[1:])

        # Main Phone
        details["main_phone"] = tree.xpath('string(//*[text()="Phone"]/../../../td[3])')

        # Main Email
        details["main_email"] = tree.xpath('string(//*[text()="Email"]/../../../td[3])')

        # ## Core - Positional:

        # Full Name
        details["name"] = tree.xpath("string(//*[@id='divProfile0']//tr[1]/td[2]/label)")
        # Known As
        details["known_as"] = tree.xpath("string(//*[@id='divProfile0']//tr[2]/td[2]/label)")
        # Join Date
        details["join_date"] = parse(tree.xpath("string(//*[@id='divProfile0']//tr[4]/td[2]/label)"))

        # ## Position Varies:

        # Gender
        details["sex"] = tree.xpath("string(//*[@id='divProfile0']//*[text()='Gender:']/../../td[2])")
        # DOB
        details["birth_date"] = parse(tree.xpath("string(//*[@id='divProfile0']//*[text()='Date of Birth:']/../../td[2])"))
        # Nationality
        details["nationality"] = tree.xpath("string(//*[@id='divProfile0']//*[text()='Nationality:']/../../td[2])")
        # Ethnicity
        details["ethnicity"] = tree.xpath("normalize-space(//*[@id='divProfile0']//*[text()='Ethnicity:']/../../td[2])")
        # Religion
        details["religion"] = tree.xpath("normalize-space(//*[@id='divProfile0']//*[text()='Religion/Faith:']/../../td[2])")
        # Occupation
        details["occupation"] = tree.xpath("normalize-space(//*[@id='divProfile0']//*[text()='Occupation:']/../../td[2])")
        # Address
        details["address"] = tree.xpath('string(//*[text()="Address"]/../../../td[3])')

        # Filter out keys with no value.
        return {k: v for k, v in details.items() if v}

    def get_roles_tab(self, membership_num: int, keep_non_volunteer_roles: bool = False) -> dict[int, dict[str, Union[int, str, datetime.datetime]]]:
        """
        Returns data from Roles tab for a given member.

        Sanitises the data to a common format, and removes Occasional Helper, Network, and PVG roles by default.

        Args:
            membership_num: Membership Number to use
            keep_non_volunteer_roles: Keep Helper (OH/PVG) & Network roles?

        Returns:
            A dict of dicts mapping keys to the corresponding data from the roles tab.

            E.g.:
            {1234578:
             {'role_number': 1234578,
              'membership_number': ...,
              'role_name': '...',
              'role_class': '...',
              'role_type': '...',
              'location_id': ...,
              'location_name': '...',
              'role_start_date': datetime.datetime(...),
              'role_end_date': datetime.datetime(...),
              'role_status': '...'},
             {...}
            }


            Keys will always be present.

        Raises:
            PermissionError:
                Access to the member is not given by the current authentication

        Todo:
            Other possible exceptions? i.e. from Requests
        """
        print(f"getting roles tab for member number: {membership_num}")
        response = self._get_member_profile_tab(membership_num, "Roles")
        tree = html.fromstring(response)

        if tree.forms[0].action == "./ScoutsPortal.aspx?Invalid=AccessCN":
            raise PermissionError(f"You do not have permission to the details of {membership_num}")

        roles_data = {}
        rows = tree.xpath("//tbody/tr")
        for row in rows:
            # Get children (cells in row)
            cells = list(row)

            # If current role allows selection of role for editing, remove tickbox
            if len(cells[0].xpath("./label")) < 1:
                cells.pop(0)

            role_number = cast(row.get("data-pk"))  # TODO cast() or int()?
            roles_data[role_number] = {
                "role_number": role_number,
                "membership_number": membership_num,
                "role_name": cells[0].text_content().strip(),
                "role_class": cells[1].text_content().strip(),
                # role_type only visible if access to System Admin tab
                "role_type": [*row.xpath("./td[1]/*/@title"), None][0],
                # location_id only visible if role is in hierarchy AND location still exists
                "location_id": cells[2][0].get("data-ng_id"),
                "location_name": cells[2].text_content().strip(),
                "role_start_date": _parse(cells[3].text_content().strip()),
                "role_end_date": _parse(cells[4].text_content().strip()),
                "role_status": cells[5].text_content().strip(),
            }

        if not keep_non_volunteer_roles:
            # Remove OHs from list
            filtered_data = {}
            for role_number, role_details in roles_data.items():

                if "helper" in role_details["role_class"].lower():
                    continue

                role_title = role_details["role_name"].lower()
                if "occasional helper" in role_title:
                    continue

                if "pvg" in role_title:
                    continue

                if "network member" in role_title:
                    continue

                filtered_data[role_number] = role_details
            roles_data = filtered_data
        return roles_data

    def get_training_tab(self, membership_num: int, ongoing_only: bool = False) -> dict[str, dict[Union[int, str], Union[dict, list]]]:
        """
        Returns data from Training tab for a given member.

        Args:
            membership_num: Membership Number to use
            ongoing_only: Return a dataframe of role training & OGL info? Otherwise returns all data

        Returns:
            A dict mapping keys to the corresponding data from the training
            tab.

            E.g.:
            {'roles': {1234567: {'role_number': 1234567,
               'title': '...',
               'start_date': datetime.datetime(...),
               'status': '...',
               'location': '...',
               'ta_data': '...',
               'ta_number': '...',
               'ta_name': '...',
               'completion': '...',
               'wood_badge_number': '...'},
              ...},
             'plps': {1234567: [{'pk': 6142511,
                'module_id': ...,
                'code': '...',
                'name': '...',
                'learning_required': False,
                'learning_method': '...',
                'learning_completed': '...',
                'validated_membership_number': '...',
                'validated_name': '...'},
               ...],
              ...},
             'mandatory': {'GDPR':
              {'name': 'GDPR',
              'completed_date': datetime.datetime(...)},
              ...}}

            Keys will always be present.

        Todo:
            Other possible exceptions? i.e. from Requests
        """
        response = self._get_member_profile_tab(membership_num, "Training")
        tree = html.fromstring(response)

        rows = tree.xpath("//table[@id='tbl_p5_TrainModules']/tr")
        roles = [row for row in rows if "msTR" in row.classes]

        personal_learning_plans = [row for row in rows if "trPLP" in row.classes]

        training_plps = {}
        training_gdpr = []
        for plp in personal_learning_plans:
            plp_table = plp.getchildren()[0].getchildren()[0]
            plp_data = []
            content_rows = [row for row in plp_table if "msTR trMTMN" == row.get("class")]
            for module_row in content_rows:
                module_data = {}
                child_nodes = list(module_row)
                module_data["pk"] = cast(module_row.get("data-pk"))
                module_data["module_id"] = cast(child_nodes[0].get("id")[4:])
                matches = re.match(r"^([A-Z0-9]+) - (.+)$", child_nodes[0].text_content()).groups()
                if matches:
                    module_data["code"] = str(matches[0])
                    module_data["name"] = matches[1]

                    # Skip processing if we only want ongoing learning data and the module
                    # is not GDPR.
                    if ongoing_only and "gdpr" not in module_data["code"].lower():
                        continue

                module_data["learning_required"] = "yes" in child_nodes[1].text_content().lower()
                module_data["learning_method"] = child_nodes[2].text_content()
                module_data["learning_completed"] = child_nodes[3].text_content()
                with contextlib.suppress(ValueError):
                    module_data["learning_date"] = datetime.datetime.strptime(child_nodes[3].text_content(), "%d %B %Y")

                validated_by_string = child_nodes[4].text_content()
                validated_by_data = validated_by_string.split(" ", maxsplit=1) + [""]  # Add empty item to prevent IndexError
                module_data["validated_membership_number"] = cast(validated_by_data[0])
                module_data["validated_name"] = validated_by_data[1]
                with contextlib.suppress(ValueError):
                    module_data["validated_date"] = datetime.datetime.strptime(child_nodes[5].text_content(), "%d %B %Y")

                plp_data.append(module_data)

                # Save GDPR validations
                if module_data.get("code").upper() == "GDPR":
                    training_gdpr.append(module_data.get("validated_date"))

            training_plps[int(plp_table.get("data-pk"))] = plp_data

        training_ogl = {}
        ongoing_learning_rows = tree.xpath("//tr[@data-ng_code]")
        for ongoing_learning in ongoing_learning_rows:
            cell_text = {c.get("id"): c.text_content() for c in ongoing_learning}
            cell_text = {k.split("_")[0] if isinstance(k, str) else k: v for k, v in cell_text.items()}

            ogl_data = {
                "name": cell_text.get(None),
                "completed_date": datetime.datetime.strptime(cell_text.get("tdLastComplete"), "%d %B %Y"),
                "renewal_date": datetime.datetime.strptime(cell_text.get("tdRenewal"), "%d %B %Y"),
            }

            training_ogl[ongoing_learning.get("data-ng_code")] = ogl_data
            # TODO missing data-pk from list(cell)[0].tag == "input", and module names/codes. Are these important?

        # Handle GDPR:
        sorted_gdpr = sorted([date for date in training_gdpr if isinstance(date, datetime.date)], reverse=True)  # Get latest GDPR date
        gdpr_date = sorted_gdpr[0] if sorted_gdpr else None
        training_ogl["GDPR"] = {
            "name": "GDPR",
            "completed_date": gdpr_date,
        }

        if ongoing_only:
            return training_ogl

        training_roles = {}
        for role in roles:
            child_nodes = list(role)

            info = {}  # NoQA

            info["role_number"] = int(role.xpath("./@data-ng_mrn")[0])
            info["title"] = child_nodes[0].text_content()
            info["start_date"] = datetime.datetime.strptime(child_nodes[1].text_content(), "%d %B %Y")
            info["status"] = child_nodes[2].text_content()
            info["location"] = child_nodes[3].text_content()

            training_advisor_string = child_nodes[4].text_content()
            info["ta_data"] = training_advisor_string
            training_advisor_data = training_advisor_string.split(" ", maxsplit=1) + [""]  # Add empty item to prevent IndexError
            info["ta_number"] = training_advisor_data[0]
            info["ta_name"] = training_advisor_data[1]

            completion_string = child_nodes[5].text_content()
            info["completion"] = completion_string
            if completion_string:
                parts = completion_string.split(":")
                info["completion_type"] = parts[0].strip()
                info["completion_date"] = datetime.datetime.strptime(parts[1].strip(), "%d %B %Y")
                info["ct"] = parts[3:]  # TODO what is this? From CompassRead.php
            info["wood_badge_number"] = child_nodes[5].get("id")

            training_roles[info["role_number"]] = info

        training_data = {
            "roles": training_roles,
            "plps": training_plps,
            "mandatory": training_ogl,
        }

        return training_data

    def get_permits_tab(self, membership_num: int) -> list:
        """
        Returns data from Permits tab for a given member.

        Args:
            membership_num: Membership Number to use

        Returns:
            A list of dicts mapping keys to the corresponding data from the
            permits tab.

            Keys will always be present.

        Todo:
            Other possible exceptions? i.e. from Requests
        """
        response = self._get_member_profile_tab(membership_num, "Permits")
        tree = html.fromstring(response)

        # Get rows with permit content
        rows = tree.xpath('//table[@id="tbl_p4_permits"]//tr[@class="msTR msTRPERM"]')

        permits = []
        for row in rows:
            permit = {}
            child_nodes = list(row)
            permit["permit_type"] = child_nodes[1].text_content()
            permit["category"] = child_nodes[2].text_content()
            permit["type"] = child_nodes[3].text_content()
            permit["restrictions"] = child_nodes[4].text_content()
            permit["expires"] = datetime.datetime.strptime(child_nodes[5].text_content(), "%d %B %Y")
            permit["status"] = child_nodes[5].get("class")

            permits.append(permit)

        return permits

    # See getAppointment in PGS\Needle
    def get_roles_detail(
            self,
            role_number: int,
            response: Union[str, requests.Response] = None
    ) -> dict:
        """
        Returns detailed data from a given role number.

        Args:
            role_number: Role Number to use
            response: Pre-generated response to use

        Returns:
            A dicts mapping keys to the corresponding data from the
            role detail data.

            E.g.:
            {'hierarchy': {'organisation': 'The Scout Association',
              'country': '...',
              'region': '...',
              'county': '...',
              'district': '...',
              'group': '...',
              'section': '...'},
             'details': {'role_number': ...,
              'organisation_level': '...',
              'dob': datetime.datetime(...),
              'member_number': ...,
              'member_name': '...',
              'role_title': '...',
              'start_date': datetime.datetime(...),
              'status': '...',
              'line_manager_number': ...,
              'line_manager': '...',
              'ce_check': datetime.datetime(...),
              'disclosure_check': '...',
              'references': '...',
              'appointment_panel_approval': '...',
              'commissioner_approval': '...',
              'committee_approval': '...'},
             'getting_started': {...: {'name': '...',
               'validated': datetime.datetime(...),
               'validated_by': '...'},
               ...
              }}

            Keys will always be present.

        Todo:
            Other possible exceptions? i.e. from Requests
        """
        renamed_levels = {
            "County / Area / Scottish Region / Overseas Branch": "County",
        }
        renamed_modules = {
            1: "module_01",
            2: "module_02",
            "M03": "module_03",
            4: "module_04",
        }
        unset_vals = {"--- Not Selected ---", "--- No Items Available ---", "--- No Line Manager ---"}

        module_names = {
            "Essential Information": "M01",
            "PersonalLearningPlan": "M02",
            "Tools for the Role (Section Leaders)": "M03",
            "Tools for the Role (Managers and Supporters)": "M04",
            "General Data Protection Regulations": "GDPR",
        }

        references_codes = {
            "NC": "Not Complete",
            "NR": "Not Required",
            "RR": "References Requested",
            "S": "References Satisfactory",
            "U": "References Unsatisfactory",
        }

        start_time = time.time()
        if response is None:
            response = self._get(f"{Settings.base_url}/Popups/Profile/AssignNewRole.aspx?VIEW={role_number}")
            print(f"Getting details for role number: {role_number}. Request in {(time.time() - start_time):.2f}s")

        post_response_time = time.time()
        if isinstance(response, (str, bytes)):
            tree = html.fromstring(response)
        else:
            tree = html.fromstring(response.content)
        form = tree.forms[0]

        member_string = form.fields.get("ctl00$workarea$txt_p1_membername")
        ref_code = form.fields.get("ctl00$workarea$cbo_p2_referee_status")

        # Approval and Role details
        role_details = {
            "role_number": role_number,
            "organisation_level": form.fields.get("ctl00$workarea$cbo_p1_level"),
            "dob": _parse(form.inputs["ctl00$workarea$txt_p1_membername"].get("data-dob")),
            "member_number": cast(form.fields.get("ctl00$workarea$txt_p1_memberno")),
            "member_name": member_string.split(" ", maxsplit=1)[1],
            "role_title": form.fields.get("ctl00$workarea$txt_p1_alt_title"),
            "start_date": _parse(form.fields.get("ctl00$workarea$txt_p1_startdate")),
            # Role Status
            "status": form.fields.get("ctl00$workarea$txt_p2_status"),
            # Line Manager
            "line_manager_number": cast(form.fields.get("ctl00$workarea$cbo_p2_linemaneger")),
            "line_manager": form.inputs["ctl00$workarea$cbo_p2_linemaneger"].xpath("string(*[@selected])"),
            # Review Date
            "review_date": form.fields.get("ctl00$workarea$txt_p2_review"),
            # CE (Confidential Enquiry) Check
            "ce_check": _parse(form.fields.get("ctl00$workarea$txt_p2_cecheck")),  # TODO if CE check date != current date then is valid
            # Disclosure Check
            "disclosure_check": form.fields.get("ctl00$workarea$txt_p2_disclosure"),
            # References
            "references": references_codes.get(ref_code, ref_code),
            # Appointment Panel Approval
            "appointment_panel_approval": tree.xpath("string(//*[@data-app_code='ROLPRP|AACA']//*[@selected])"),
            # Commissioner Approval
            "commissioner_approval": tree.xpath("string(//*[@data-app_code='ROLPRP|CAPR']//*[@selected])"),
            # Committee Approval
            "committee_approval": tree.xpath("string(//*[@data-app_code='ROLPRP|CCA']//*[@selected])"),
        }

        line_manager_number = role_details["line_manager_number"]
        if line_manager_number in unset_vals:
            role_details["line_manager_number"] = None

        # Getting Started
        modules_output = {}
        getting_started_modules = tree.xpath("//tr[@class='trTrain trTrainData']")
        # Get all training modules and then extract the required modules to a dictionary
        for module in getting_started_modules:
            module_name = module.xpath("string(./td/label/text())")
            if module_name in module_names:
                short_name = module_names[module_name]
                info = {
                    "name": short_name,
                    "validated": _parse(module.xpath("./td[3]/input/@value")[0]),  # Save module validation date
                    "validated_by": module.xpath("./td/input[2]/@value")[0],  # Save who validated the module
                }
                mod_code = cast(module.xpath("./td[3]/input/@data-ng_value")[0])
                modules_output[renamed_modules.get(mod_code, mod_code)] = info

        # Filter null values
        role_details = {k: v for k, v in role_details.items() if v is not None}

        # Get all levels of the org hierarchy and select those that will have information:
        # Get all inputs with location data
        org_levels = [v for k, v in sorted(dict(form.inputs).items()) if "ctl00$workarea$cbo_p1_location" in k]
        # TODO
        all_locations = {row.get("title"): row.findtext("./option") for row in org_levels}

        clipped_locations = {
            renamed_levels.get(key, key).lower(): value for key, value in all_locations.items() if value not in unset_vals
        }

        print(f"Processed details for role number: {role_number}. Compass: {(post_response_time - start_time):.3f}s; Processing: {(time.time() - post_response_time):.4f}s")
        # TODO data-ng_id?, data-rtrn_id?
        # return {**clipped_locations, **role_details, **modules_output}
        return {"hierarchy": clipped_locations, "details": role_details, "getting_started": modules_output}