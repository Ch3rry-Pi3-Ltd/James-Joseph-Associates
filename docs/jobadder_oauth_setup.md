# JobAdder OAuth Application Setup

This document captures the practical setup work completed so far for the
JobAdder developer application and the backend callback route.

It sits between:

- the earlier JobAdder discovery notes
- the backend API contract
- the live deployment notes

In plain language:

- this document answers the question:

    "What did we do to get the JobAdder app and OAuth callback set up, and what happens next?"

- it does not contain secrets
- it does not contain real tokens
- it does not contain real client data

## 1. Why This Setup Exists

JobAdder's API is protected by OAuth.

That means we cannot simply start calling the API from a script or from the
browser.

We first need:

1. a registered JobAdder developer application
2. authorised redirect URIs
3. backend environment variables
4. a real backend callback route
5. a later server-side token exchange step

The important distinction is:

- the **company website URLs** describe who built the app
- the **redirect URI** tells JobAdder where to send the user back after access
  is approved

## 2. What We Did So Far

### Developer and application registration

We:

- registered the JobAdder developer account
- created the JobAdder application
- used company URLs for homepage, privacy, terms, and logo
- registered both local and live redirect URIs

The app was registered as:

```text
Ch3rry Pi3 JJA Integration Dev
```

The short description used was:

```text
Server-side JobAdder integration for securely accessing and reconciling recruitment data to support workflow automation, reporting, and intelligent search.
```

### Company-facing application URLs used

These values describe the app owner / legal surface, not the backend callback:

```text
Home Page URL  -> https://www.ch3rry-pi3.com
Privacy URL    -> https://www.ch3rry-pi3.com/privacy-policy
Terms URL      -> https://www.ch3rry-pi3.com/terms
Logo URL       -> https://www.ch3rry-pi3.com/logos/ch3rry-pi3-logo.jpg
```

### Redirect URIs used

These values describe where JobAdder sends the user back after successful
authorisation:

```text
https://james-joseph-associates.vercel.app/api/v1/integrations/jobadder/callback
http://127.0.0.1:8000/api/v1/integrations/jobadder/callback
http://localhost:8000/api/v1/integrations/jobadder/callback
```

The live URI is the important production-facing callback.

The localhost URIs are useful for local development and debugging.

## 3. Backend Work Completed

We added a real callback route at:

```text
GET /api/v1/integrations/jobadder/callback
```

That route is implemented in:

```text
backend/api/v1/integrations.py
```

The route currently:

- accepts the callback path
- accepts a `code` query parameter
- handles provider-side `error` query parameters clearly
- checks whether the backend has the minimum OAuth settings configured
- returns a structured JSON response

It does **not** yet:

- exchange the authorisation code for tokens
- store tokens
- start pulling JobAdder entities

That was deliberate. Exchanging the one-time code before token storage exists
would be sloppy and hard to recover from cleanly.

## 4. Environment Variables Now In Use

The backend now expects:

```text
JOBADDER_CLIENT_ID
JOBADDER_CLIENT_SECRET
JOBADDER_REDIRECT_URI
```

For the current live app, the redirect value should be:

```text
JOBADDER_REDIRECT_URI="https://james-joseph-associates.vercel.app/api/v1/integrations/jobadder/callback"
```

## 5. Vercel Notes

The JobAdder variables were added to Vercel.

One practical wrinkle showed up:

- Vercel marked these values as sensitive
- those sensitive values were available for `Production` and `Preview`
- they were not available for `Development`

That meant:

```powershell
vercel env pull .env.local
```

did not bring them down locally, because that command pulls the development
environment by default.

The working local pull was:

```powershell
vercel env pull .env.local --environment=production
```

After that, the local backend saw the values correctly.

## 6. Useful Smoke Checks

### Local callback check

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/integrations/jobadder/callback?code=test-code"
```

Expected result now:

- `authorization_code_received = True`
- `oauth_configuration_ready = True`

### Live callback check

```text
https://james-joseph-associates.vercel.app/api/v1/integrations/jobadder/callback
```

If visited without a real OAuth code, the expected response is a validation
error saying the authorisation code is required.

That is acceptable. It proves:

- the live callback route exists
- Vercel is routing to the backend correctly
- the route is not a placeholder

## 7. What We Have Proved

So far we have proved:

- the JobAdder developer application is registered
- the application URLs are set
- the redirect URIs are set
- the local callback route is live
- the live Vercel callback route is live
- the backend can read the JobAdder OAuth settings
- the backend can distinguish "callback reached" from "OAuth flow completed"

## 8. What Is Next

The next engineering step is:

1. receive the real JobAdder `code`
2. exchange that code server-side for tokens
3. store the returned tokens safely
4. use those tokens to make the first real JobAdder API calls

After that, the next functional milestone is:

- reading real JobAdder data safely
- starting with a narrow, controlled read path
- validating the canonical model against the real source payloads

## 9. Current Position In Simple Terms

So far, we have built the secure front door.

What is still missing is the part where the backend:

- takes the real key from JobAdder
- swaps it for access tokens
- starts opening the door properly
