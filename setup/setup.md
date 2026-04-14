# Project Setup

<details open>
<summary><strong>1. Vercel CLI Setup</strong></summary>

Use this section to install and authenticate the Vercel CLI from the project terminal.

<details open>
<summary><strong>Current Local Status</strong></summary>

Current setup state:

- The local folder is linked to the Vercel project `james-joseph-associates`.
- Vercel created `.vercel/project.json`.
- The local Vercel project metadata currently points to:
  - Project name: `james-joseph-associates`
  - Project ID: stored in `.vercel/project.json`
  - Org/team ID: stored in `.vercel/project.json`
- Vercel environment metadata has been pulled into `.env.local`.
- `.env.local` currently includes `VERCEL_OIDC_TOKEN`.
- Supabase environment variables have been pulled into `.env.local`.
- Supabase/Postgres variables now include names such as `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `POSTGRES_URL`, and `POSTGRES_PRISMA_URL`.
- `.env.local`, `.env*.local`, and `.vercel` are ignored by Git.

Important:

- Do not commit `.env.local`.
- Do not copy secret values into documentation.
- It is acceptable to document environment variable names, but not their values.

</details>

<details open>
<summary><strong>1.1 Confirm Node and npm Are Available</strong></summary>

Run:

```powershell
node --version
npm --version
```

Expected outcome:

- Node.js returns a version number.
- npm returns a version number.

If either command is not recognised, install Node.js before continuing.

</details>

<details open>
<summary><strong>1.2 Install the Vercel CLI</strong></summary>

Run:

```powershell
npm install -g vercel
```

Expected outcome:

- The Vercel CLI is installed globally.
- The `vercel` command becomes available in the terminal.

</details>

<details open>
<summary><strong>1.3 Log In to Vercel</strong></summary>

Run:

```powershell
vercel login
```

Expected outcome:

- Vercel opens an authentication flow.
- The terminal confirms that login succeeded.
- The authenticated Vercel account has access to the intended project/team.

</details>

<details>
<summary><strong>1.4 Link the Local Folder to a Vercel Project</strong></summary>

Run this from the project root:

```powershell
vercel link
```

Recommended answers:

- Set up the current directory when prompted.
- Choose the correct Vercel scope or team.
- Link to an existing project only if it already exists in Vercel.
- Otherwise create a new project, for example `james-joseph-associates`.
- Use `./` as the project directory unless the application is later scaffolded in a subdirectory.

Note: this repository is currently in the planning/documentation phase. Linking the Vercel project is fine, but deployment should wait until there is an actual backend/app to build.

</details>

<details>
<summary><strong>1.5 Pull Vercel Environment Metadata</strong></summary>

After the project is linked, run:

```powershell
vercel env pull .env.local
```

Expected outcome:

- Vercel creates or updates `.env.local`.
- Local development can use the same environment variable names as the Vercel project.
- At this stage, `.env.local` may contain Vercel-managed values such as `VERCEL_OIDC_TOKEN`.

Important:

- Do not commit `.env.local`.
- Do not commit `.env*.local`.
- Do not commit secret values.
- Keep required environment variable names documented separately from their values.

To inspect environment variable names without printing values, run:

```powershell
Get-Content .env.local | ForEach-Object { if ($_ -match '^\s*#|^\s*$') { $_ } elseif ($_ -match '^\s*([^=]+)=') { $Matches[1] + '=<redacted>' } else { '<redacted>' } }
```

</details>

<details open>
<summary><strong>1.6 Connect the GitHub Repository to Vercel</strong></summary>

During `vercel link`, Vercel may ask:

```text
Detected a repository. Connect it to this project?
```

Answer:

```text
Y
```

For this project, the expected repository is:

```text
https://github.com/Ch3rry-Pi3-Ltd/James-Joseph-Associates.git
```

If Vercel returns an error such as:

```text
Failed to connect Ch3rry-Pi3-Ltd/James-Joseph-Associates to project. Make sure there aren't any typos and that you have access to the repository if it's private.
```

The local Vercel project may still be linked successfully. Check for:

```powershell
Get-Content .vercel\project.json
```

If `.vercel/project.json` exists, the local folder is linked to the Vercel project. The remaining issue is the **GitHub integration permissions**.

Recommended fix:

- Open the Vercel dashboard.
- Open the `james-joseph-associates` project.
- Go to the project **Git** settings.
- Connect the GitHub repository manually.
- If prompted, install or update the Vercel GitHub app for the `Ch3rry-Pi3-Ltd` GitHub organisation.
- Ensure the Vercel GitHub app has access to `Ch3rry-Pi3-Ltd/James-Joseph-Associates`.
- Ensure the GitHub user connecting the repo has sufficient access to the repository, especially if it is private.

If PowerShell blocks the Vercel CLI shim with an execution policy error, use:

```powershell
vercel.cmd --version
```

and run Vercel commands with `vercel.cmd` instead of `vercel`.

</details>

<details open>
<summary><strong>1.7 Find Marketplace / Integrations in Vercel</strong></summary>

Vercel shows **Integrations** on the main dashboard view. Supabase is then listed under **Marketplace** as a **Native Integration**.

Browser route:

- Open `https://vercel.com/dashboard`.
- Confirm the selected scope/team is the one that owns `james-joseph-associates`.
- From the main dashboard sidebar, select **Integrations**.
- In the Integrations area, find **Native Integrations**.
- Select **Supabase** from the Native Integrations list.
- Choose the `james-joseph-associates` Vercel project when prompted.

Direct Marketplace page:

```text
https://vercel.com/marketplace/supabase
```

CLI fallback:

```powershell
vercel.cmd integration discover
```

If Supabase appears in the list, start the interactive setup with:

```powershell
vercel.cmd integration add supabase
```

After the Supabase integration is added, pull the updated environment variables:

```powershell
vercel.cmd env pull .env.local
```

Notes:

- Use `vercel.cmd` on this Windows machine if PowerShell blocks the `vercel` script shim.
- Vercel's Marketplace storage integrations can automatically inject credentials into connected projects as environment variables.
- If the CLI prompts for a project, choose `james-joseph-associates`.

</details>

</details>

<details open>
<summary><strong>2. Supabase Marketplace Integration</strong></summary>

Use this section to connect Supabase to the Vercel project as a **Native Integration**.

<details open>
<summary><strong>2.1 Install Supabase from Vercel Marketplace</strong></summary>

Dashboard route:

- Open the Vercel dashboard.
- Use the main dashboard sidebar, not only the individual project settings.
- Select **Integrations**.
- In **Native Integrations**, select **Supabase**.
- Click **Install**.
- In the product installation flow, choose the `james-joseph-associates` Vercel project.
- Create or connect the Supabase project as prompted.
- Use **London, United Kingdom (West)** as the primary database region.
- Keep the public environment variable prefix as `NEXT_PUBLIC_`.
- Use the **Supabase Free Plan** during setup and early Phase 1 unless project requirements justify an upgrade.

Notes from the Vercel Marketplace page:

- Supabase is listed as a **Postgres backend**.
- Plans start at `$0`, but pricing and usage limits should still be reviewed before production use.
- The integration can sync project environment variables into Vercel automatically.
- The integration can support redirect URL setup for Supabase preview branches.

</details>

<details open>
<summary><strong>2.2 Connect Supabase to the Vercel Project</strong></summary>

In the **Install Integration** flow, use these settings:

- Project: `james-joseph-associates`
- Environments:
  - Development
  - Preview
  - Production
- Supabase Preview Branch:
  - Leave disabled for now unless branch-specific Supabase databases are explicitly needed.
- Custom Prefix:
  - Keep the default `STORAGE` prefix unless there is a clear reason to change it.

Rationale:

- All three environments should have the database variables available because the backend will eventually need development, preview, and production configuration.
- Supabase Preview Branches add useful isolation later, but they are unnecessary complexity during initial setup.
- Keeping the default prefix reduces naming surprises from the Vercel integration.

</details>

<details open>
<summary><strong>2.3 Expected Supabase Environment Variables</strong></summary>

The Vercel Supabase integration documents the following environment variable names:

```text
POSTGRES_URL
POSTGRES_PRISMA_URL
POSTGRES_URL_NON_POOLING
POSTGRES_USER
POSTGRES_HOST
POSTGRES_PASSWORD
POSTGRES_DATABASE
SUPABASE_SERVICE_ROLE_KEY
SUPABASE_ANON_KEY
SUPABASE_URL
SUPABASE_JWT_SECRET
NEXT_PUBLIC_SUPABASE_ANON_KEY
NEXT_PUBLIC_SUPABASE_URL
```

Important:

- Treat these as **secret or sensitive** unless clearly public.
- Do not commit their values.
- Do not paste their values into documentation, GitHub issues, Slack, or chat.
- The `NEXT_PUBLIC_*` values are designed for frontend exposure, but they should still be used intentionally.
- `SUPABASE_SERVICE_ROLE_KEY`, `POSTGRES_PASSWORD`, and `SUPABASE_JWT_SECRET` are especially sensitive.

</details>

<details open>
<summary><strong>2.4 Pull Supabase Environment Variables Locally</strong></summary>

After installing the Supabase integration, run:

```powershell
vercel.cmd env pull .env.local
```

Vercel's Supabase quickstart may show this variant:

```powershell
vercel env pull .env.development.local
```

For this project, either filename can work, but use **one convention consistently**. The current local setup uses:

```powershell
.env.local
```

Then inspect names only, with values redacted:

```powershell
Get-Content .env.local | ForEach-Object { if ($_ -match '^\s*#|^\s*$') { $_ } elseif ($_ -match '^\s*([^=]+)=') { $Matches[1] + '=<redacted>' } else { '<redacted>' } }
```

Expected outcome:

- `.env.local` contains `VERCEL_OIDC_TOKEN`.
- `.env.local` contains the Supabase/Postgres variables listed above.
- `.env.local` remains ignored by Git.

</details>

<details open>
<summary><strong>2.5 Supabase Quickstart Guidance</strong></summary>

The Supabase/Vercel integration page may show a generic quickstart with steps such as:

- Create a sample `notes` table.
- Add a public read RLS policy.
- Create a Next.js app with a Supabase template.
- Add a sample `app/notes/page.tsx`.
- Run `npm run dev`.

For this project, **do not follow those sample app/table steps yet** unless we explicitly decide to scaffold the application.

Reason:

- This repository is still in the **planning and setup phase**.
- We do not want to create throwaway schema such as `notes`.
- We do not want to scaffold a Next.js app until the backend structure and Phase 1 data model are agreed.
- The first real Supabase schema should be based on the recruitment GraphRAG model, not a tutorial table.

What does make sense now:

- Install the Supabase integration.
- Connect it to `james-joseph-associates`.
- Pull environment variables locally.
- Confirm the environment variable names are present.
- Defer schema/app creation until the Phase 1 implementation plan starts.

</details>

<details>
<summary><strong>2.6 Vendor Quickstart Reference Notes</strong></summary>

These notes preserve useful details from the Supabase/Vercel vendor quickstart. They are **reference only**, not current project implementation instructions.

Potentially useful details for later:

- The vendor quickstart suggests pulling environment variables with:

```powershell
vercel env pull .env.development.local
```

- The vendor quickstart uses a sample `notes` table to prove the integration works.
- The sample SQL shape is:

```sql
create table notes (
  id bigint primary key generated always as identity,
  title text not null
);
```

- The sample data insert shape is:

```sql
insert into notes (title)
values
  ('Today I created a Supabase project.'),
  ('I added some data and queried it from Next.js.'),
  ('It was awesome!');
```

- The sample RLS policy shape is:

```sql
alter table notes enable row level security;

create policy "public can read notes"
on public.notes
for select to anon
using (true);
```

- The vendor quickstart also suggests creating a Next.js app with the Supabase template.
- The template is preconfigured for:
  - Cookie-based auth.
  - TypeScript.
  - Tailwind CSS.
- The sample app then queries Supabase data from a route such as `app/notes/page.tsx`.
- The sample dev flow runs:

```powershell
npm run dev
```

Do not apply this directly to the project without revisiting the Phase 1 architecture. The real schema should be based on the recruitment GraphRAG data model, not the sample `notes` table.

</details>

</details>
