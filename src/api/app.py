import uvicorn
from fastapi import FastAPI, APIRouter

from src.api.routes import members

app = FastAPI()

version_one = APIRouter()

version_one.include_router(
    members.router,
    prefix="/members",
    tags=["Members"],
    dependencies=[],
    responses={404: {"description": "Not found!"}}
)

app.include_router(
    version_one,
    prefix="/v1",
    dependencies=[]
)

# Appointments report - role details (except M01Ex, M04), ongoing details (except M01Ex imputing), disclosures
# Member Directory - emergency contact details
# Permit Report - permits
# Training Report - training


# base = api.compass.cys.org.uk
# /v1/
#    /members/me
#    /members/{memberNumber}
#            /XXX/ - default is profile ✔
#                /roles ✔
#                /ongoing-training ✔
#                /disclosures
#                /training
#                /permits
#                /awards
#                /emergency_details          ??
#                /communication_preferences  ??
#                /visibility                 ??
#                /compliance_data            ??
#                /training_data              ??
#                /awards_data                ??
#    /hierarchy/
#              /organisations
#              /countries
#              /regions
#              /counties  - symlinks for Areas/Scot Region/Islands/Bailiwicks?
#              /districts
#              /groups
#              /XXX/children
#              /XXX/sections
#              /XXX/members
#    /reports/{reportType}/
#    /


if __name__ == '__main__':
    uvicorn.run("app:app", host='0.0.0.0', port=8000)
    print()