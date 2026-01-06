## Comment out whenever you have done any of the below points.

#Current Requirements
1. Proposals generated with separate are not showing different dates. Explanation below.
#Future Requirements

1. Companies Endpoint with all company details and the methods  - I can see that in /dev/companies path - confirm if this is correct. 
2. User - multiple Profile set and list
3. User - multiple Permission set
4. Profile - Profile to permission-sets relation
5. Hide teams, sharing rules etc which we are not using for now.
6. While saving the template images, can you also save a thumbnail for the templates so that the templates can load faster. Something like xxxx_n_thumb.png. Just include it with the existing response, as Thumbnail. I can then load both.
7. History for Mockups with data and the image that was generated.
8. There is an edit option for the mockup templates, Do you have any endpoint where the frame details and config is available for a particular template?


## Proposal Generation - Separate

Send request with payload : 

{
    "proposals": [
        {
            "location":"oryx",
            "upload_fee":"AED 1,500",
            "spots":1,
            "start_dates":["01/01/2026","01/02/2026","01/03/2026"],
            "durations":["2 Weeks","2 Weeks","3 Weeks"],
            "net_rates":["AED 12,000","AED 13,000","AED 32,000"]
        },
        {
            "location":"the_helix",
            "upload_fee":"AED 3,000",
            "spots":2,
            "start_dates":["02/01/2026"],
            "durations":["3 Weeks"],
            "net_rates":["AED 23,000"]
        }
    ],
    "client_name":"Etisalat",
    "proposal_type":"separate",
    "payment_terms":"70% upfront, 30% after",
    "currency":"AED"
}


Generated Output : https://hqhwddnaynbimltpqlli.supabase.co/storage/v1/object/sign/uploads/proposals/ee7eabae-3214-4364-8e48-12b8ffc0532a/2026/01/06/ad7ca9ff-cdc4-427a-b4de-7f2c1ee8f471_Etisalat_11596126.pdf?token=eyJraWQiOiJzdG9yYWdlLXVybC1zaWduaW5nLWtleV8wNTU0MzQ3My1kOWExLTRiNWYtYWRmYS1lNGEzODQ4ZmM0ZDUiLCJhbGciOiJIUzI1NiJ9.eyJ1cmwiOiJ1cGxvYWRzL3Byb3Bvc2Fscy9lZTdlYWJhZS0zMjE0LTQzNjQtOGU0OC0xMmI4ZmZjMDUzMmEvMjAyNi8wMS8wNi9hZDdjYTlmZi1jZGM0LTQyN2EtYjRkZS03ZjJjMWVlOGY0NzFfRXRpc2FsYXRfMTE1OTYxMjYucGRmIiwiaWF0IjoxNzY3Njg2MzY5LCJleHAiOjE3Njc3NzI3Njl9.pRALK7EgGuIKPXM1moF7f-_GwriVeRhvI1dHcIdcc9I


 - Missing multiple start dates. Payment terms are set to 100% upfront and not as per request. 

## Combined works perfectly.

Request
{
    "proposals": [
        {
            "location": "oryx",
            "upload_fee": "AED 1,500",
            "spots": 1,
            "start_date": "01/01/2026",
            "duration": "2 Weeks"
        },
        {
            "location": "the_helix",
            "upload_fee": "AED 3,000",
            "spots": 2,
            "start_date": "02/01/2026",
            "duration": "3 Weeks"
        }
    ],
    "client_name": "Etisalat",
    "proposal_type": "combined",
    "payment_terms": "70% upfront, 30% after",
    "currency": "AED",
    "combined_net_rate": "AED 450,000.16"
}

Response : 

https://hqhwddnaynbimltpqlli.supabase.co/storage/v1/object/sign/uploads/proposals/ee7eabae-3214-4364-8e48-12b8ffc0532a/2026/01/06/d5b29e8b-944c-4e1b-9151-f8241a5af20d_Du_12116126.pdf?token=eyJraWQiOiJzdG9yYWdlLXVybC1zaWduaW5nLWtleV8wNTU0MzQ3My1kOWExLTRiNWYtYWRmYS1lNGEzODQ4ZmM0ZDUiLCJhbGciOiJIUzI1NiJ9.eyJ1cmwiOiJ1cGxvYWRzL3Byb3Bvc2Fscy9lZTdlYWJhZS0zMjE0LTQzNjQtOGU0OC0xMmI4ZmZjMDUzMmEvMjAyNi8wMS8wNi9kNWIyOWU4Yi05NDRjLTRlMWItOTE1MS1mODI0MWE1YWYyMGRfRHVfMTIxMTYxMjYucGRmIiwiaWF0IjoxNzY3Njg3MTE0LCJleHAiOjE3Njc3NzM1MTR9.20PRNW1I1sbZZW3KHBCYajHt7Wy3shzeCICYA4UWuxw


Request

{
    "proposals": [
        {
            "location": "oryx",
            "upload_fee": "AED 1,500",
            "spots": 1,
            "start_date": "01/01/2026",
            "duration": "2 Weeks"
        },
        {
            "location": "uae04",
            "upload_fee": "AED 0",
            "spots": 2,
            "production_fee": "AED 5,000",
            "start_date": "02/01/2026",
            "duration": "3 Weeks"
        }
    ],
    "client_name": "Du",
    "proposal_type": "combined",
    "payment_terms": "70% upfront, 30% after",
    "currency": "AED",
    "combined_net_rate": "AED 440,000"
}


Response : 


https://hqhwddnaynbimltpqlli.supabase.co/storage/v1/object/sign/uploads/proposals/ee7eabae-3214-4364-8e48-12b8ffc0532a/2026/01/06/76ce87e0-e41d-4d6e-9fac-cb81b8e922dd_Etisalat_12106126.pdf?token=eyJraWQiOiJzdG9yYWdlLXVybC1zaWduaW5nLWtleV8wNTU0MzQ3My1kOWExLTRiNWYtYWRmYS1lNGEzODQ4ZmM0ZDUiLCJhbGciOiJIUzI1NiJ9.eyJ1cmwiOiJ1cGxvYWRzL3Byb3Bvc2Fscy9lZTdlYWJhZS0zMjE0LTQzNjQtOGU0OC0xMmI4ZmZjMDUzMmEvMjAyNi8wMS8wNi83NmNlODdlMC1lNDFkLTRkNmUtOWZhYy1jYjgxYjhlOTIyZGRfRXRpc2FsYXRfMTIxMDYxMjYucGRmIiwiaWF0IjoxNzY3Njg3MDA5LCJleHAiOjE3Njc3NzM0MDl9.4OKeClR5ICdFdrIUbCIIQxckvew0yJPPenRP99j8DUI

