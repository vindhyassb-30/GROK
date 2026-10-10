=================================================================
CRYSTAL BALL - API PAYLOAD REFERENCE (app_v2.py)
Base URL (local): http://localhost:5001
All request bodies are JSON (Content-Type: application/json).
=================================================================

AUTHENTICATION (JWT)
-----------------------------------------------------------------
1. Call /login with user_id + password. The response contains a "token".
2. Store the token on the frontend (e.g. sessionStorage).
3. Send it on every endpoint marked [AUTH] below, as a header:

       Authorization: Bearer <token>

4. The token is valid for 8 hours. After that, [AUTH] endpoints return
   401 "Token expired, please log in again" -> send the user back to /login.

The logged-in user's details come FROM THE TOKEN, not from the request body.
/unique-shipment and /unique-invoice are filtered by PlantKey == user_name
(Admin sees all plants).

Do NOT send these fields any more (they are ignored if sent):
  - /raise-ticket          : ticket_raised_by, raised_by_category, action_by
  - /update-ticket-status  : action_by
  - /user-tickets          : user

Frontend example:
  fetch("/raise-ticket", {
      method: "POST",
      headers: {
          "Content-Type": "application/json",
          "Authorization": "Bearer " + sessionStorage.getItem("token")
      },
      body: JSON.stringify({ ...payload })
  });

[AUTH] error responses (401):
  - "Missing or malformed Authorization header"  -- no header / not "Bearer <token>"
  - "Invalid token"                              -- token altered or signed with another secret
  - "Token expired, please log in again"         -- older than 8 hours


QUICK INDEX
-----------------------------------------------------------------
 #   Method     URL                              Purpose
-----------------------------------------------------------------
 1   POST       /login                           Log in, get token + user details
 1b  GET        /me                     [AUTH]   Logged-in user's details
 2   GET/POST   /unique-shipment        [AUTH]   Shipment ids (SH...) for the user's PlantKey
 3   GET/POST   /unique-invoice         [AUTH]   Invoice numbers for the user's PlantKey
 3b  GET/POST   /unique-material        [AUTH]   All distinct material codes (YVR18 + forecast)
 4   GET/POST   /test/dispatch-summary           Shipment details (materials, source, destination)
 5   POST       /find-correct-invoice            Find the right invoice from date + materials
 6   GET/POST   /inserting-record                Add a remark to a shipment + material
 7   GET/POST   /all-record-for-shipment         Get remarks for a shipment
 8   POST       /raise-ticket           [AUTH]   Raise one or more tickets for a shipment
 9   POST       /tickets-for-shipment            List ticket ids for a shipment
10   POST       /update-ticket-status   [AUTH]   Move a ticket to Investigate / Closed / Reopen
11   GET        /ticket-history/<ticket_id>      Full timeline of one ticket
12   POST       /user-tickets           [AUTH]   Tickets raised by + raised against the logged-in user
13   GET        /ticket-stats                    Ticket counts + tickets that crossed SLA  (NOT LIVE YET)
14   GET        /admin/user-names       [ADMIN]  Site user_names + their user_type (Add User dropdown)
15   POST       /admin/add-user         [ADMIN]  Create a new login user

[ADMIN] = [AUTH] + the logged-in user's user_type must be "Admin", otherwise
          403 "Only Admin can perform this action".
-----------------------------------------------------------------

Typical ticket flow on the frontend:
  /login -> /unique-shipment -> /test/dispatch-summary -> /raise-ticket
  -> /tickets-for-shipment or /user-tickets -> /update-ticket-status -> /ticket-history/<ticket_id>


-----------------------------------------------------------------
1) LOGIN
-----------------------------------------------------------------
Method : POST
URL    : /login

Request payload:
{
    "user_id": "",       -- required, e.g. "gjr2_user@apollotyres.com"
    "password": ""       -- required
}

Sample response:
{
    "status": "success",
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",   -- send as "Authorization: Bearer <token>"
    "data": {
        "user_id": "gjr2_user@apollotyres.com",
        "user_type": "RDC",         -- e.g. "RDC" | "AO" | "Admin" | "FGS_Limda"
        "user_name": "GJR2"         -- used as ticket_raised_by on /raise-ticket
    }
}

"data" is for display only (e.g. "Welcome, GJR2"). The backend always uses
the values inside the token.

Errors:
  - 401 "Invalid user_id or password"
  - 400 "Missing field: 'user_id'" / "Missing field: 'password'"


-----------------------------------------------------------------
1b) LOGGED-IN USER                                           [AUTH]
-----------------------------------------------------------------
Method : GET
URL    : /me
Header : Authorization: Bearer <token>

Request payload: none

Use after a page refresh to get the user's details back from the stored token.

Sample response:
{
    "status": "success",
    "data": {
        "user_id": "gjr2_user@apollotyres.com",
        "user_type": "RDC",
        "user_name": "GJR2"
    }
}

Errors:
  - 401 (see AUTHENTICATION section)


-----------------------------------------------------------------
2) UNIQUE SHIPMENT LIST
-----------------------------------------------------------------
Method : GET / POST
URL    : /unique-shipment
Header : Authorization: Bearer <token>                       [AUTH]

Request payload: none

Only shipment ids starting with "SH" are returned, and only for the
logged-in user's plant: t_scm_dispatch_YVR18 rows where PlantKey == user_name
(e.g. user_name "GJR2" -> PlantKey "GJR2"). Admin users get all plants.

Sample response:
{
    "unique_shipment": ["SH1004200726008", "SH1004200726009"]
}


-----------------------------------------------------------------
3) UNIQUE INVOICE LIST
-----------------------------------------------------------------
Method : GET / POST
URL    : /unique-invoice
Header : Authorization: Bearer <token>                       [AUTH]

Request payload: none

Only invoices for the logged-in user's plant: t_scm_dispatch_YVR18 rows where
PlantKey == user_name. Admin users get all plants.

Sample response:
{
    "unique_invoice": ["226300780", "226300781"]
}


-----------------------------------------------------------------
3b) UNIQUE MATERIAL LIST                                     [AUTH]
-----------------------------------------------------------------
Method : GET / POST
URL    : /unique-material
Header : Authorization: Bearer <token>

Request payload: none

Overall distinct material codes from both sources:
  - t_scm_dispatch_YVR18  -> MaterialKey
  - forecast_input_merged -> ProductId
Union of both, sorted; blanks and "#" removed. Not filtered by plant.

Sample response:
{
    "unique_material": ["LS1004INCOK200726001", "RTB6R0ELD1AJ1"],
    "total": 2,
    "dispatch_count": 1,      -- distinct codes found in YVR18
    "forecast_count": 2       -- distinct codes found in forecast_input_merged
}


-----------------------------------------------------------------
4) DISPATCH SUMMARY (shipment details)
-----------------------------------------------------------------
Method : GET / POST
URL    : /test/dispatch-summary

Request payload:
{
    "filter_category": "",     -- required: "ShipmentId" | "InvoiceNumber"
    "filter_value": ""         -- required: the shipment id or invoice number
}

Sample response (key inside "data" is the filter_value that was sent):
{
    "status": "success",
    "data": {
        "SH1004200726008": {
            "Container_details": "[{'MaterialID': '', 'MaterialDescription': '', 'total_count': 0, 'Dispatched_date': ''}]",
            "Source":      {"code": "GJR2",   "label": "",   "city": ""},
            "Destination": {"code": "ZCGJ09", "label": "DO", "city": "Porbandar"},
            "Unique_materialid": ["All", "LS1004INCOK200726001"]
        }
    }
}

Source / Destination come from the dispatch data (t_scm_dispatch_YVR18),
looked up with the same filter that was sent (OTMShipID or InvoiceNumber).
Freight data is not used; ETA and freight_data_available are no longer returned.
  - Source.code        = PlantKey                          e.g. "GJR2"
    Source.label/city  = "" (not available in dispatch data)
  - Destination.code   = CustomerNumberKey                 e.g. "ZCGJ09"
  - Destination.label  = RecPlantCustomerKey before ","    e.g. "DO"
  - Destination.city   = RecPlantCustomerKey after ","     e.g. "Porbandar"


NOTE: Container_details is currently returned as a STRING (Python list text),
not a JSON array.

Errors:
  - 400 "filter_category is required" / "filter_value is required"


-----------------------------------------------------------------
5) FIND CORRECT INVOICE (by date + material/quantity match)
-----------------------------------------------------------------
Method : POST
URL    : /find-correct-invoice

Use this when the invoice number on file might be wrong. Checks every invoice
dispatched on BillDate and returns the one whose full material + quantity
list matches exactly.

Request payload:
{
    "BillDate": "",            -- required, same format as stored, e.g. "22.09.2026"
    "materials": [             -- required
        {
            "MaterialId": "",
            "quantity": ""
        }
    ]
}

Sample response (match found):
{
    "status": "success",
    "data": {"matched": true, "invoice_number": "226300780"}
}

Sample response (no match):
{
    "status": "success",
    "data": {
        "matched": false,
        "reason": "No invoice on this date matches the given material/quantity combination",
        "invoice_number": null
    }
}

Sample response (more than one match):
{
    "status": "success",
    "data": {
        "matched": false,
        "reason": "Multiple invoices matched - cannot uniquely identify the correct invoice",
        "invoice_number": null,
        "candidates": []
    }
}

Errors:
  - 400 "Missing field: 'BillDate'" / "Missing field: 'materials'"


-----------------------------------------------------------------
6) INSERT REMARK FOR A SHIPMENT
-----------------------------------------------------------------
Method : GET / POST
URL    : /inserting-record

Request payload:
{
    "ShipmentId": "",
    "MaterialId": "",
    "Remark": ""               -- required
}

Sample response:
{
    "status": "success",
    "Message": "New Record is created for <ShipmentId>-<MaterialId> into the database "
}
(If a record already exists for that shipment + material, the remark is appended
and the message says "New Remark was appended into ...".)


-----------------------------------------------------------------
7) FETCH REMARKS FOR A SHIPMENT
-----------------------------------------------------------------
Method : GET / POST
URL    : /all-record-for-shipment

Request payload:
{
    "ShipmentId": "",
    "MaterialId": ""           -- optional. Omit or send null to get remarks for all materials
}

Sample response (remarks found):
{
    "status": "success",
    "records": [
        {
            "Shipmentid": "",
            "MaterialId": "",
            "Remarks": [
                {"Time": "2026-09-29 10:00:00", "Remark": ""}
            ]
        }
    ]
}

Sample response (nothing found):
{
    "status": "success",
    "records": "No remark"
}


-----------------------------------------------------------------
8) RAISE TICKET                                              [AUTH]
-----------------------------------------------------------------
Method : POST
URL    : /raise-ticket
Header : Authorization: Bearer <token>

Raises one or more tickets for ONE shipment in a single request. Send one row per
material inside "material_data" (always a list, even for one material). Each row
can have a different Category.

Do NOT send ticket_id, ticket_number or ticket_uuid. The backend generates:
  - ticket_id     : "<InvoiceNumber>-<Material>-<Category>"
                    e.g. "226300780-LS1004INCOK200726001-Shortage"
                    (tickets raised before this change keep the old
                     "<ship_id>-<Material>-<Category>" id)
                    (spaces in Category become "_", e.g. "...-Generic_Complaint")
  - ticket_number : "ATL-1", "ATL-2", ...  (sequential across all tickets)
  - ticket_uuid   : unique id per ticket

Filled automatically from the logged-in user's token (do NOT send):
  - ticket_raised_by   = user_name   e.g. "GJR2"
  - raised_by_category = user_type   e.g. "RDC"
  - action_by          = user_name   e.g. "GJR2"  (recorded in ticket_history)

Request payload:
{
    "ship_id": "",                  -- required
    "invoice_number": "",           -- optional, invoice for all rows (see "Invoice number" below)
    "ticket_raised_against": "",    -- required, user_name of the other side, e.g. "AP01"
    "against_category": "",         -- required, user_type of the other side, e.g. "AO"
    "material_data": [              -- required, non-empty list
        {
            "Material": "",
            "InvoiceNumber": "",    -- optional, overrides invoice_number for this row
            "Category": "",         -- "Excess" | "Shortage" | "Variation" | "Damage" | "Generic Complaint"
            "Remark": "",
            "Actual": "",
            "Expected": ""
        }
    ]
}

Required fields per Category (inside each material_data row):
  - Excess            : Material, Actual, Expected
  - Shortage          : Material, Actual, Expected
  - Variation         : Material, Remark
  - Damage            : Material, Remark
  - Generic Complaint : Material, Remark
Category must match exactly (same capitals and spacing).

Invoice number (used at the start of ticket_id and stored on the ticket):
  1. InvoiceNumber on the material_data row, if sent
  2. else invoice_number at shipment level, if sent
  3. else looked up in t_scm_dispatch_YVR18 by ship_id + Material
     - one invoice found       -> used
     - several invoices found  -> row fails, send invoice_number
     - nothing found           -> row fails

ticket_raised_against must use the same user_name value stored in the users
collection (e.g. "AP01"), otherwise that user will not see the ticket in
/user-tickets.

Example (logged in as gjr2_user@apollotyres.com -> user_name "GJR2", user_type "RDC"):
{
    "ship_id": "SH1004200726008",
    "ticket_raised_against": "AP01",
    "against_category": "AO",
    "material_data": [
        {"Material": "LS1004INCOK200726001", "Category": "Shortage", "Remark": "20 short", "Actual": 480, "Expected": 500},
        {"Material": "LS1004INCOK200726002", "Category": "Damage", "Remark": "", "Actual": "", "Expected": ""}
    ]
}
Stored ticket gets: ticket_raised_by "GJR2", Raised_by_category "RDC", action_by "GJR2",
InvoiceNumber looked up from YVR18 (e.g. "226300780").

Sample response (one result per row, "index" = position in "material_data"):
{
    "status": "success",
    "results": [
        {"index": 0, "ticket_id": "226300780-LS1004INCOK200726001-Shortage",
         "ticket_number": "ATL-1", "ticket_uuid": "", "status": "created", "action": "Created"},
        {"index": 1, "status": "failed", "reason": "Invalid record: Damage requires: remark"}
    ]
}

Possible "reason" values for failed rows:
  - "Invalid record: Unknown Category: ..."      -- Category not in the allowed list
  - "Invalid record: <Category> requires: ..."   -- a required field for that Category is empty
  - "Duplicate ticket in same request"           -- same Material + Category twice in the list
  - "Active ticket already exists (status: ..)"  -- ticket is Open / Investigate / Reopen
  - "Missing field: ..."                         -- a shipment-level field is missing
  - "Invoice number not found for this shipment + material"
                                                 -- not in YVR18 and not sent
  - "Material is on multiple invoices for this shipment (A, B); send invoice_number"

Request-level errors (whole request rejected):
  - 400 "ship_id is required"
  - 400 "'material_data' must be a non-empty list"
  - 401 missing / invalid / expired token (see AUTHENTICATION section)

NOTE: Each row succeeds or fails on its own; one bad row does not block the others.
If a ticket already exists for the same ticket_id and is NOT "Closed", it is rejected.
If it is "Closed", submitting again reopens it and keeps the same ticket_id,
ticket_number and ticket_uuid (action = "Reopened").


-----------------------------------------------------------------
9) GET TICKET IDs FOR A SHIPMENT
-----------------------------------------------------------------
Method : POST
URL    : /tickets-for-shipment

Use this to fill a ticket selector before calling /ticket-history or
/update-ticket-status.

Request payload:
{
    "ShipmentId": ""           -- required
}

Sample response:
{
    "status": "success",
    "ticket_ids": [
        "226300780-LS1004INCOK200726001-Shortage",
        "226300780-LS1004INCOK200726001-Damage"
    ]
}

Errors:
  - 400 "ShipmentId is required"


-----------------------------------------------------------------
10) UPDATE TICKET STATUS (Investigate / Closed / Reopen)     [AUTH]
-----------------------------------------------------------------
Method : POST
URL    : /update-ticket-status
Header : Authorization: Bearer <token>

action_by is filled automatically with the logged-in user's user_name
(e.g. "AP01") and recorded in ticket_history. Do NOT send it.

Request payload:
{
    "ticket_id": "",       -- required, e.g. "226300780-LS1004INCOK200726001-Shortage"
    "new_status": "",      -- required: "Investigate" | "Closed" | "Reopen"
    "remark": ""           -- optional
}

Sample response:
{
    "status": "success",
    "data": {
        "ticket_id": "226300780-LS1004INCOK200726001-Shortage",
        "current_status": "Investigate"
    }
}

Errors:
  - 404 "Ticket not found"
  - 400 "Missing field: 'ticket_id'" / "'new_status'"
  - 401 missing / invalid / expired token

NOTE: new_status is not validated yet. Send exactly one of the values above.


-----------------------------------------------------------------
11) GET TICKET HISTORY (full timeline / audit trail)
-----------------------------------------------------------------
Method : GET
URL    : /ticket-history/<ticket_id>
Header : Authorization: Bearer <token>                       [AUTH]

Request payload: none (ticket_id goes in the URL)

Example:
GET /ticket-history/226300780-LS1004INCOK200726001-Shortage

Sample response (oldest first):
{
    "status": "success",
    "history": [
        {
            "ticket_id": "226300780-LS1004INCOK200726001-Shortage",
            "ticket_number": "ATL-1",
            "ticket_uuid": "",
            "InvoiceNumber": "226300780",
            "ShipmentId": "SH1004200726008",
            "status": "Open",
            "action": "Created",
            "action_by": "GJR2",
            "remark": "20 short",
            "timestamp": "2026-09-29 10:00:00"
        },
        {
            "ticket_id": "226300780-LS1004INCOK200726001-Shortage",
            "ticket_number": "ATL-1",
            "ticket_uuid": "",
            "InvoiceNumber": "226300780",
            "ShipmentId": "SH1004200726008",
            "status": "Investigate",
            "action": "Investigate",
            "action_by": "AP01",
            "remark": "Checking dispatch records",
            "timestamp": "2026-09-30 09:15:00"
        }
    ],
    "is_eligible_to_remark": 0
}

"history" is returned exactly as stored. Next to it (not inside it):

  "is_eligible_to_remark": 0 | 1
     0 = the LATEST history entry's action_by is the logged-in user
         (they made the last move, so it is the other side's turn)
     1 = the latest entry was made by someone else
     0 = the ticket has no history
  Example above, viewed by AP01 -> 0 ; viewed by GJR2 -> 1.
  This is a UI flag only; /update-ticket-status does not enforce it.

An unknown ticket_id returns "history": [] and "is_eligible_to_remark": 0 (not a 404).
Errors:
  - 401 missing / invalid / expired token


-----------------------------------------------------------------
12) TICKETS FOR THE LOGGED-IN USER (raised by + raised against)   [AUTH]
-----------------------------------------------------------------
Method : POST
URL    : /user-tickets
Header : Authorization: Bearer <token>

The user is taken from the token (user_name, e.g. "GJR2"). Do NOT send "user".

Returns two lists from ticket_current, newest first:
  - ticket_raised_by      : tickets where ticket_raised_by      == user_name
  - ticket_raised_against : tickets where ticket_raised_against == user_name

Request payload:
{
    "status": ""       -- optional: "Active" | "Investigate" | "Closed" | "Reopen"
                           omit or send "" (or send {}) to get all statuses
}

Sample response:
{
    "status": "success",
    "data": {
        "ticket_raised_by": [
            {
                "ticket_id": "", "ticket_number": "", "ticket_uuid": "", "InvoiceNumber": "", "ShipmentId": "",
                "variation_category": "", "MaterialId": "", "actual_value": "", "expected_value": "",
                "ticket_raised_against": "", "Against_category": "",
                "ticket_raised_by": "", "Raised_by_category": "",
                "current_status": "", "created_at": "", "updated_at": ""
            }
        ],
        "ticket_raised_against": []
    }
}

Errors:
  - 401 missing / invalid / expired token


-----------------------------------------------------------------
13) TICKET STATS                                   ** NOT LIVE YET **
-----------------------------------------------------------------
Method : GET
URL    : /ticket-stats

Request payload: none

Counts every ticket in ticket_current and lists the tickets that crossed SLA.

How each number is calculated:
  - total_count        : all tickets
  - active_count       : status "Open" + "Reopen"
  - investigate_count  : status "Investigate"
  - closed_count       : status "Closed"
  - crossed_sla_count  : NOT "Closed" and created_at is more than sla_days (3) days ago

Sample response:
{
    "status": "success",
    "data": {
        "total_count": 12,
        "active_count": 5,
        "investigate_count": 3,
        "closed_count": 4,
        "sla_days": 3,
        "crossed_sla_count": 2,
        "crossed_sla_tickets": [
            {
                "ticket_id": "226300780-LS1004INCOK200726001-Shortage",
                "ticket_number": "ATL-1",
                "ShipmentId": "SH1004200726008",
                "current_status": "Open",
                "created_at": "2026-09-24 10:00:00"
            }
        ]
    }
}

crossed_sla_tickets is sorted oldest first.


-----------------------------------------------------------------
14) ADMIN - USER NAMES FOR "ADD USER" DROPDOWN               [ADMIN]
-----------------------------------------------------------------
Method : GET
URL    : /admin/user-names
Header : Authorization: Bearer <admin token>

Request payload: none

Call this when the admin opens the "Add User" screen. Returns every allowed
user_name (SiteID) with the user_type it maps to. The list is hardcoded in the
backend (SITE_USER_TYPES in ticket_assign.py), built from the Apollo Facility
Master (Type "ABU" is shown as "AO"). "Admin" is always the last option.

Sample response (sorted by user_name):
{
    "status": "success",
    "data": [
        {"user_name": "1001",  "user_type": "FGS"},
        {"user_name": "AP01",  "user_type": "AO"},
        {"user_name": "GJR2",  "user_type": "RDC"},
        {"user_name": "NDC1",  "user_type": "NDC"},
        ...
        {"user_name": "Admin", "user_type": "Admin"}
    ]
}

Frontend usage:
  - Fill the user_name dropdown from data[].user_name
  - When a user_name is selected, auto-fill user_type from the same item
    (show it read-only; the admin does not choose it)

Errors:
  - 401 missing / invalid / expired token
  - 403 "Only Admin can perform this action"


-----------------------------------------------------------------
15) ADMIN - ADD USER                                         [ADMIN]
-----------------------------------------------------------------
Method : POST
URL    : /admin/add-user
Header : Authorization: Bearer <admin token>

Creates one login user in the users collection. The new user can log in
via /login straight away.

Request payload:
{
    "user_id": "",      -- required, email, e.g. "gjr2_manager@apollotyres.com"
                           (stored lowercase; must not already exist)
    "password": "",     -- required, at least 7 characters
    "user_name": "",    -- required, one of the user_name values from /admin/user-names
    "user_type": ""     -- optional, the value auto-filled from /admin/user-names.
                           The backend always decides user_type from user_name;
                           if this is sent and does not match, the request is rejected.
}

Example payload:
{
    "user_id": "gjr2_manager@apollotyres.com",
    "password": "GJR2x#7k",
    "user_name": "GJR2",
    "user_type": "RDC"
}

Sample response (201 Created):
{
    "status": "success",
    "data": {
        "user_id": "gjr2_manager@apollotyres.com",
        "user_name": "GJR2",
        "user_type": "RDC"
    }
}

Stored document (users collection):
{
    "user_id": "gjr2_manager@apollotyres.com",
    "password": "GJR2x#7k",
    "user_type": "RDC",
    "user_name": "GJR2",
    "created_at": "2026-09-29 10:00:00"
}

Errors:
  - 400 "user_id, password and user_name are required"
  - 400 "user_id must be an email address"
  - 400 "password must be at least 7 characters"
  - 400 "Unknown user_name '<value>'. Pick one from /admin/user-names"
  - 400 "user_type for '<user_name>' must be '<type>', got '<sent type>'"
  - 409 "user_id '<email>' already exists"
  - 401 missing / invalid / expired token
  - 403 "Only Admin can perform this action"

Typical "Add User" flow on the frontend:
  click "Add User" -> GET /admin/user-names -> fill dropdown
  -> admin enters user_id + password, picks user_name (user_type auto-fills)
  -> POST /admin/add-user -> show success or the error message


=================================================================
TICKET STATUS VALUES
=================================================================
Active | Investigate | Closed | Reopen


=================================================================
TICKET CATEGORY VALUES
=================================================================
Excess | Shortage | Variation | Damage | Generic Complaint


=================================================================
ERROR RESPONSE (all endpoints)
=================================================================
{
    "status": "error",
    "message": ""
}
HTTP codes: 400 = bad/missing input,
            401 = login failed, or missing / invalid / expired token,
            403 = logged in but not allowed (e.g. non-Admin on /admin/*),
            404 = not found, 409 = already exists (e.g. user_id on /admin/add-user),
            500 = server error
