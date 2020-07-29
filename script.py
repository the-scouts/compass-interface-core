from src.compass.hierarchy import CompassHierarchy
from src.compass.logon import CompassLogon
from src.compass.people import CompassPeople
from src.compass.reports import get_report
from src.interface import compass_read


if __name__ == '__main__':
    auth_keys = ['user', 'pass']
    compass_role_to_use = 'Regional Administrator'
    # compass_role_to_use = 'HQ Committee Member - Scout Grants Committee'
    # compass_role_to_use = 'Country Scout Active Support Member'
    # compass_role_to_use = 'County Executive Committee Member'
    # compass_read(auth_keys)
    c_logon = CompassLogon(auth_keys, compass_role_to_use)
    # hierarchy = CompassHierarchy(c_logon.session)
    # people = CompassPeople(c_logon.session)
    # b = people.get_member_data(12047820)
    # a = people._scraper.get_roles_detail(2155910)
    # a = people._scraper.get_roles_detail(760357)
    # a = people.get_member_data(760357)

    get_report(c_logon)

    # SCRATCH #
    leah_sier_id = 11861706
    # a = people._roles_tab(leah_sier_id)
    # b = people.get_member_data(leah_sier_id)
    print()

    # Get all units within a given OU
    # print("Compliance for Cook Meth")
    # cook_meth_compliance = create_compliance_data_for_unit(10013849)
    # cook_meth_compliance.to_csv("cmsg.csv", index=False, encoding="utf-8-sig")
    surrey_county_id = 10000115
    banstead_district_id = 10001222
    cook_meth_id = 10013849
    # surrey_county_id = 10000115
    # cook_meth_id = 10013849
    # surrey_hierarchy = hierarchy.get_hierarchy(cook_meth_id, "Group")
    # table_surrey = hierarchy.hierarchy_to_dataframe(surrey_hierarchy)
    # print(table_surrey)

    # Get all members within that OU  (5020s ~= 1.5 hours for FULL ORG)
    # surrey_members = hierarchy.get_all_members_table(cook_meth_id, table_surrey["compass"])

    # Get all roles within that OU (0.25s per unique member)
    # surrey_roles = people.get_roles_from_members(cook_meth_id, surrey_members["contact_number"])

    print("STOPPED")

    # TODO auto relogon
    # TODO

    # View org entities : https://compass.scouts.org.uk/Popups/Maint/NewOrgEntity.aspx?VIEW=10000001
    # View section ents : https://compass.scouts.org.uk/Popups/Maint/NewSection.aspx?VIEW=11851927

    # View member : https://compass.scouts.org.uk/MemberProfile.aspx?CN=183755
    # View permits: https://compass.scouts.org.uk/MemberProfile.aspx?CN=183755&Page=PERMITS&TAB
    # View awards : https://compass.scouts.org.uk/MemberProfile.aspx?CN=183755&Page=AWARDS&TAB
    # View DBS    : https://compass.scouts.org.uk/MemberProfile.aspx?CN=183755&Page=DISCLOSURES&TAB

    # View permit detail : https://compass.scouts.org.uk/Popups/Maint/NewPermit.aspx?CN=12047820&VIEW=64093&UseCN=849454
