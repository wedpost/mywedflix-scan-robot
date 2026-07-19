# mywedflix face-scan robot 🤖

Ye robot **GitHub ke free servers** pe har 30 minute chalta hai aur aapke saare
premieres ke naye photos ka face-scan **khud** kar deta hai — koi page, koi
computer khula rakhne ki zaroorat nahi.

## Setup (ek baar, ~10 minute)

1. **github.com** pe account banao (free) — agar pehle se hai to login.

2. Naya repository banao: upar-right **+** → **New repository**
   - Name: `mywedflix-scan-robot`
   - **Public** rakho — public repos pe GitHub Actions ke minutes UNLIMITED free hain
     (token repo me nahi hota, sirf Secrets me — isliye public rakhna safe hai)
   - **Create repository**

3. Is folder ki **teeno cheezein** upload karo:
   repo page pe **uploading an existing file** link → ye files drag karo:
   - `scan.py`  (naya ArcFace robot — pehle se zyada accurate)
   - `requirements.txt`
   - `.github` folder (poora — isme workflows/scan.yml hai)

   > Agar browser se `.github` folder upload na ho to: **Add file → Create new file**,
   > naam me type karo `.github/workflows/scan.yml` aur scan.yml ka content paste kar do.

4. **Secret token** daalo:
   repo me **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `MW_TOKEN`
   - Value: Downloads me `mywedflix-TOKEN.txt` file me likha token
     (wo file jaan-boojh kar is folder se BAHAR hai — repo me kabhi upload nahi hogi)
   - **Add secret**

5. **Actions tab** kholo → agar "enable workflows" pooche to enable karo →
   left me **face-scan** → **Run workflow** (pehla run haath se chala kar dekh lo).

Bas. Ab har 30 minute me robot khud check karega — Drive/Photos me nayi photos
dali to sirf wahi scan hongi, sab ho chuka to seconds me so jayega.

> Pehla run thoda lamba (~1-2 min) hoga — InsightFace ka model download hota hai,
> phir wo cache ho jata hai aur agle run fast hote hain. Yehi robot guests ke
> selfie enrollment bhi process karta hai (photos dhoondhne ke liye).

## Kaise pata chalega ki chal raha hai?

- GitHub me **Actions** tab — har run ka log: kaunsa premiere, kitni photos, kitne faces
- Superadmin → **🧠 Face scans** tab — har premiere ka status wahi dikhta rahega

## Notes

- **Public repo = unlimited free minutes.** Logs public hote hain, lekin robot
  unme kuch bhi private nahi likhta (codes masked, tokens kabhi nahi).
- **Zyada privacy chahiye?** Repo **Private** rakho + `scan.yml` me cron
  `*/30 * * * *` ki jagah `0 * * * *` (har ghante) kar do — free 2,000 min me
  ~60,000 photos/month ka scan aa jata hai, aur logs sirf aapko dikhte hain.
- GitHub 60 din tak repo me koi activity na ho to schedule ko pause kar deta hai
  (email aata hai) — kabhi bhi README me ek space add karke commit kar dena, phir chalu
- Ab **sirf yehi robot** face-scan karta hai — purana browser-wala scanner (premiere
  kholne par / Scanner page) band kar diya gaya hai (wo kam-accurate 128-dim tha).
  Scanner aur Face-scan page ab sirf **live status** dikhate hain.
- Site ka password/database robot ke paas NAHI hai — sirf scan-only token hai
