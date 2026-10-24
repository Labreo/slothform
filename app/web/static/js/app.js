/**
 * SlothForm Web Dashboard Application
 * Connects to FastAPI REST backend and streams real-time SSE telemetry.
 * Fully interactive Identity Vault & Profile Setup with AES-256 persistence.
 * Adheres to Refero Styles AgentQL Design System (Zero Emojis, Midnight Terminal).
 */

document.addEventListener("DOMContentLoaded", () => {
  // Navigation Tabs & Views
  const tabBtnRunner = document.getElementById("tab-btn-runner");
  const tabBtnSetup = document.getElementById("tab-btn-setup");
  const runnerView = document.getElementById("runner-view");
  const setupView = document.getElementById("setup-view");
  const activeProfilePill = document.getElementById("active-profile-pill");
  const runnerEditProfileBtn = document.getElementById("runner-edit-profile-btn");

  // Runner Form & Controls
  const form = document.getElementById("fill-form");
  const targetUrlInput = document.getElementById("target-url-input");
  const dryRunToggle = document.getElementById("dry-run-toggle");
  const dryRunLabel = document.getElementById("dry-run-status-text");
  const submitBtn = document.getElementById("submit-btn");
  const progressBar = document.getElementById("stage-progress-bar");
  const statusText = document.getElementById("pipeline-status-text");
  const terminalLogs = document.getElementById("terminal-logs");
  const replayContainer = document.getElementById("replay-container");
  const replayFrame = document.getElementById("browserbase-replay-frame");
  const replayLiveDot = document.getElementById("replay-live-dot");
  const diffTbody = document.getElementById("diff-tbody");
  const diffModal = document.getElementById("diff-inspection-modal");
  const modalCloseBtn = document.getElementById("modal-close-btn");
  const modalCloseActionBtn = document.getElementById("modal-close-action-btn");
  const viewDiffBtn = document.getElementById("view-diff-btn");

  // CIBA Consent Elements
  const cibaConsentCard = document.getElementById("ciba-consent-card");
  const cibaTimerBadge = document.getElementById("ciba-timer-badge");
  const cibaApproveBtn = document.getElementById("ciba-approve-btn");
  const cibaRejectBtn = document.getElementById("ciba-reject-btn");
  const cibaInspectModalBtn = document.getElementById("ciba-inspect-modal-btn");
  const modalApproveBtn = document.getElementById("modal-approve-btn");
  const modalRejectBtn = document.getElementById("modal-reject-btn");

  // Profile Setup Elements
  const profileForm = document.getElementById("profile-setup-form");
  const saveProfileBtn = document.getElementById("save-profile-btn");
  const saveProfileBtnBottom = document.getElementById("save-profile-btn-bottom");
  const goRunnerBtn = document.getElementById("go-runner-btn");
  const goRunnerBtnBottom = document.getElementById("go-runner-btn-bottom");
  const loadSampleBtn = document.getElementById("load-sample-btn");
  const clearProfileBtn = document.getElementById("clear-profile-btn");
  const vaultSaveToast = document.getElementById("vault-save-toast");
  const toastCloseBtn = document.getElementById("toast-close-btn");
  const toastActionBtn = document.getElementById("toast-action-btn");
  const toastTitle = document.getElementById("toast-title");
  const toastMessage = document.getElementById("toast-message");
  const toastIconWrap = document.getElementById("toast-icon-wrap");
  const resumeFileInput = document.getElementById("resume-file-input");
  const resumeDropzone = document.getElementById("resume-dropzone");
  const resumeUploadStatus = document.getElementById("resume-upload-status");

  // Profile Display Targets
  const headerProfileName = document.getElementById("header-profile-name");
  const runnerProfileName = document.getElementById("runner-profile-name");
  const runnerProfileEmail = document.getElementById("runner-profile-email");
  const runnerProfileMeta = document.getElementById("runner-profile-meta");

  let activeEventSource = null;
  let currentActiveTaskId = null;
  let toastTimeout = null;

  // ---------------------------------------------------------------------------
  // View & Tab Switching
  // ---------------------------------------------------------------------------
  function switchTab(target) {
    if (target === "setup") {
      if (tabBtnRunner) {
        tabBtnRunner.classList.remove("active", "bg-cobalt-panel", "border-sapphire-hairline", "text-quartz");
        tabBtnRunner.classList.add("text-ash");
      }
      if (tabBtnSetup) {
        tabBtnSetup.classList.add("active", "bg-cobalt-panel", "border-sapphire-hairline", "text-quartz");
        tabBtnSetup.classList.remove("text-ash");
      }
      if (runnerView) runnerView.style.display = "none";
      if (setupView) setupView.style.display = "block";
      loadProfileIntoForm();
    } else {
      if (tabBtnSetup) {
        tabBtnSetup.classList.remove("active", "bg-cobalt-panel", "border-sapphire-hairline", "text-quartz");
        tabBtnSetup.classList.add("text-ash");
      }
      if (tabBtnRunner) {
        tabBtnRunner.classList.add("active", "bg-cobalt-panel", "border-sapphire-hairline", "text-quartz");
        tabBtnRunner.classList.remove("text-ash");
      }
      if (setupView) setupView.style.display = "none";
      if (runnerView) runnerView.style.display = "block";
    }
  }

  if (tabBtnRunner) tabBtnRunner.addEventListener("click", () => switchTab("runner"));
  if (tabBtnSetup) tabBtnSetup.addEventListener("click", () => switchTab("setup"));
  if (goRunnerBtn) goRunnerBtn.addEventListener("click", () => switchTab("runner"));
  if (goRunnerBtnBottom) goRunnerBtnBottom.addEventListener("click", () => switchTab("runner"));
  if (toastActionBtn) toastActionBtn.addEventListener("click", () => switchTab("runner"));
  if (activeProfilePill) activeProfilePill.addEventListener("click", () => switchTab("setup"));
  if (runnerEditProfileBtn) runnerEditProfileBtn.addEventListener("click", () => switchTab("setup"));

  // ---------------------------------------------------------------------------
  // Dry-Run Toggle & Sample Chips
  // ---------------------------------------------------------------------------
  if (dryRunToggle && dryRunLabel) {
    dryRunToggle.addEventListener("change", (e) => {
      if (e.target.checked) {
        dryRunLabel.textContent = "DRY-RUN GUARD: ON";
        dryRunLabel.style.color = "var(--amber-primary)";
      } else {
        dryRunLabel.textContent = "LIVE SUBMISSION: ON";
        dryRunLabel.style.color = "var(--rose-danger)";
      }
    });
  }

  document.querySelectorAll(".quick-samples .sample-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const sampleUrl = chip.getAttribute("data-url");
      if (sampleUrl && targetUrlInput) {
        targetUrlInput.value = sampleUrl;
        targetUrlInput.focus();
        chip.style.transform = "scale(0.96)";
        setTimeout(() => {
          chip.style.transform = "";
        }, 150);
      }
    });
  });

  // ---------------------------------------------------------------------------
  // Modal Handlers
  // ---------------------------------------------------------------------------
  if (diffModal) diffModal.style.display = "none";

  function openDiffModal() {
    if (diffModal) {
      diffModal.classList.add("active");
      diffModal.style.display = "flex";
    }
  }

  function closeDiffModal() {
    if (diffModal) {
      diffModal.classList.remove("active");
      diffModal.style.display = "none";
    }
  }

  if (viewDiffBtn) viewDiffBtn.addEventListener("click", openDiffModal);
  if (cibaInspectModalBtn) cibaInspectModalBtn.addEventListener("click", openDiffModal);
  if (modalCloseBtn) modalCloseBtn.addEventListener("click", closeDiffModal);
  if (modalCloseActionBtn) modalCloseActionBtn.addEventListener("click", closeDiffModal);
  if (diffModal) {
    diffModal.addEventListener("click", (e) => {
      if (e.target === diffModal) closeDiffModal();
    });
  }

  // ---------------------------------------------------------------------------
  // Toast Notifications
  // ---------------------------------------------------------------------------
  function showToast(title, message, isSuccess = true, showAction = false) {
    if (!vaultSaveToast) return;
    if (toastTimeout) clearTimeout(toastTimeout);

    if (toastTitle) toastTitle.textContent = title;
    if (toastMessage) toastMessage.textContent = message;

    if (toastActionBtn) {
      toastActionBtn.style.display = showAction ? "inline-flex" : "none";
    }

    if (isSuccess) {
      vaultSaveToast.className = "toast-banner mt-4 p-4 rounded-xl border border-emerald-success/40 bg-deep-sea flex items-center justify-between gap-3 shadow-lg";
      if (toastIconWrap) {
        toastIconWrap.className = "w-8 h-8 rounded-lg bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center text-emerald-success shrink-0";
        toastIconWrap.innerHTML = `
          <svg class="w-4 h-4 text-emerald-success" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
        `;
      }
    } else {
      vaultSaveToast.className = "toast-banner mt-4 p-4 rounded-xl border border-rose-danger/40 bg-deep-sea flex items-center justify-between gap-3 shadow-lg";
      if (toastIconWrap) {
        toastIconWrap.className = "w-8 h-8 rounded-lg bg-rose-500/20 border border-rose-500/30 flex items-center justify-center text-rose-danger shrink-0";
        toastIconWrap.innerHTML = `
          <svg class="w-4 h-4 text-rose-danger" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"/>
            <line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        `;
      }
    }

    vaultSaveToast.style.display = "flex";
    toastTimeout = setTimeout(() => {
      vaultSaveToast.style.display = "none";
    }, 8000);
  }

  if (toastCloseBtn) {
    toastCloseBtn.addEventListener("click", () => {
      if (vaultSaveToast) vaultSaveToast.style.display = "none";
    });
  }

  // ---------------------------------------------------------------------------
  // Profile Loading & Population
  // ---------------------------------------------------------------------------
  function updateProfileDisplays(profile) {
    if (!profile || !profile.core) return;
    const name = profile.core.full_name || "Anonymous Candidate";
    const email = profile.core.email || "";
    const headline = (profile.career && profile.career.headline) || "Technology Professional";
    const country = profile.core.country || "India";
    const treaty = (profile.tax && profile.tax.tax_treaty_article) ? ` (DTAA ${profile.tax.tax_treaty_article})` : "";

    if (headerProfileName) headerProfileName.textContent = name;
    if (runnerProfileName) runnerProfileName.textContent = name;
    if (runnerProfileEmail) runnerProfileEmail.textContent = email;
    if (runnerProfileMeta) {
      runnerProfileMeta.textContent = `${headline} — ${country}${treaty}`;
    }

    document.querySelectorAll(".modal-active-name").forEach((el) => {
      el.textContent = name;
    });
    document.querySelectorAll(".modal-active-email").forEach((el) => {
      el.textContent = email;
    });
  }

  async function loadProfileIntoForm() {
    try {
      const res = await fetch("/api/vault/profile");
      if (!res.ok) throw new Error("Could not load vault profile");
      const profile = await res.json();
      populateFormFields(profile);
      updateProfileDisplays(profile);
    } catch (err) {
      console.warn("Failed to load profile from backend:", err);
    }
  }

  function setVal(id, val) {
    const el = document.getElementById(id);
    if (!el) return;
    if (el.type === "checkbox") {
      el.checked = Boolean(val);
    } else {
      el.value = val !== undefined && val !== null ? val : "";
    }
  }

  function getVal(id) {
    const el = document.getElementById(id);
    if (!el) return "";
    if (el.type === "checkbox") {
      return el.checked;
    }
    return el.value.trim();
  }

  function populateFormFields(p) {
    if (!p) return;
    const c = p.core || {};
    const car = p.career || {};
    const t = p.tax || {};
    const fin = p.financial || {};
    const qa = car.custom_qa_pairs || {};

    // Core
    setVal("core-full-name", c.full_name);
    setVal("core-email", c.email);
    setVal("core-phone", c.phone);
    setVal("core-address-line1", c.address_line1);
    setVal("core-address-line2", c.address_line2);
    setVal("core-city", c.city);
    setVal("core-state", c.state_province);
    setVal("core-postal", c.postal_code);
    setVal("core-country", c.country || "India");
    setVal("core-citizenship", c.citizenship || "India");
    setVal("core-dob", c.date_of_birth);
    setVal("core-portfolio", car.portfolio_url);
    setVal("core-linkedin", car.linkedin_url);
    setVal("core-github", car.github_url);

    // Career
    setVal("career-headline", car.headline);
    setVal("career-yoe", car.years_of_experience);
    setVal("career-bio", car.bio);
    setVal("career-work-history", car.work_history);
    setVal("career-degree", car.education_degree);
    setVal("career-university", car.education_university);
    setVal("career-grad-year", car.education_grad_year);
    setVal("career-gpa", car.education_gpa);
    setVal("career-skills", Array.isArray(car.skills) ? car.skills.join(", ") : car.skills);
    setVal("career-resume-markdown", car.resume_markdown);
    setVal("qa-why-interested", qa.why_interested);
    setVal("qa-work-auth", qa.work_authorization);

    // Tax
    setVal("tax-residence-country", t.tax_residence_country || "India");
    setVal("tax-pan", t.pan);
    setVal("tax-ssn-itin", t.ssn_itin || "");
    setVal("tax-treaty-country", t.tax_treaty_country || "India");
    setVal("tax-treaty-article", t.tax_treaty_article || "Article 12(2)");
    setVal("tax-treaty-rate", t.treaty_withholding_rate || "15%");
    setVal("tax-treaty-income-type", t.treaty_income_type || "Royalties / Independent Personal Services");
    setVal("tax-claim-benefits", t.claim_treaty_benefits !== undefined ? t.claim_treaty_benefits : true);

    // Financial
    setVal("fin-bank-name", fin.bank_name);
    setVal("fin-account-number", fin.account_number);
    setVal("fin-routing-ifsc", fin.routing_ifsc);
    setVal("fin-swift-bic", fin.swift_bic);
    setVal("fin-wise-id", fin.wise_recipient_id);
  }

  // ---------------------------------------------------------------------------
  // Profile Saving
  // ---------------------------------------------------------------------------
  async function saveProfile() {
    const fullName = getVal("core-full-name");
    const email = getVal("core-email");
    const phone = getVal("core-phone");
    const address1 = getVal("core-address-line1");
    const city = getVal("core-city");
    const state = getVal("core-state");
    const postal = getVal("core-postal");
    const country = getVal("core-country") || "India";
    const citizenship = getVal("core-citizenship") || "India";
    const headline = getVal("career-headline");
    const skillsRaw = getVal("career-skills");
    const resumeText = getVal("career-resume-markdown");

    if (!fullName || !email || !phone || !address1 || !city || !state || !postal || !headline || !skillsRaw || !resumeText) {
      showToast("Missing Required Fields", "Please fill in all required personal, career, and resume fields.", false);
      return;
    }

    // Process Skills
    const skillsList = skillsRaw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);

    // Process PAN
    let panVal = getVal("tax-pan").toUpperCase();
    if (panVal) {
      const panRegex = /^[A-Z]{5}[0-9]{4}[A-Z]{1}$/;
      if (!panRegex.test(panVal)) {
        showToast("Invalid Indian PAN", "PAN must be exactly 10 characters (5 letters, 4 digits, 1 letter, e.g. ABCDE1234F).", false);
        return;
      }
    } else {
      panVal = null;
    }

    const payload = {
      core: {
        full_name: fullName,
        email: email,
        phone: phone,
        address_line1: address1,
        address_line2: getVal("core-address-line2") || null,
        city: city,
        state_province: state,
        postal_code: postal,
        country: country,
        citizenship: citizenship,
        date_of_birth: getVal("core-dob") || null,
      },
      tax: {
        tax_residence_country: getVal("tax-residence-country") || "India",
        pan: panVal,
        ssn_itin: null,
        has_us_tax_id: false,
        tax_treaty_country: getVal("tax-treaty-country") || "India",
        tax_treaty_article: getVal("tax-treaty-article") || "Article 12(2)",
        treaty_withholding_rate: getVal("tax-treaty-rate") || "15%",
        treaty_income_type: getVal("tax-treaty-income-type") || "Royalties / Independent Personal Services",
        claim_treaty_benefits: Boolean(getVal("tax-claim-benefits")),
      },
      career: {
        headline: headline,
        years_of_experience: parseInt(getVal("career-yoe"), 10) || 0,
        skills: skillsList,
        resume_markdown: resumeText,
        github_url: getVal("core-github") || "https://github.com",
        linkedin_url: getVal("core-linkedin") || "https://linkedin.com",
        portfolio_url: getVal("core-portfolio") || null,
        work_history: getVal("career-work-history") || null,
        education_degree: getVal("career-degree") || null,
        education_university: getVal("career-university") || null,
        education_grad_year: getVal("career-grad-year") || null,
        education_gpa: getVal("career-gpa") || null,
        bio: getVal("career-bio") || null,
        custom_qa_pairs: {
          why_interested: getVal("qa-why-interested") || "Passionate about building scalable systems.",
          work_authorization: getVal("qa-work-auth") || "Independent international contractor (W-8BEN).",
        },
      },
      financial: {
        bank_name: getVal("fin-bank-name") || null,
        account_number: getVal("fin-account-number") || null,
        routing_ifsc: getVal("fin-routing-ifsc") || null,
        swift_bic: getVal("fin-swift-bic") || null,
        wise_recipient_id: getVal("fin-wise-id") || null,
      },
    };

    if (saveProfileBtn) {
      saveProfileBtn.disabled = true;
      saveProfileBtn.innerHTML = `
        <span class="inline-block animate-spin mr-1">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
        </span>
        <span>Encrypting to Vault...</span>
      `;
    }
    if (saveProfileBtnBottom) saveProfileBtnBottom.disabled = true;

    try {
      const res = await fetch("/api/vault/profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || "Failed to persist profile to vault");
      }

      const resData = await res.json();
      updateProfileDisplays(payload);
      showToast("Vault Encrypted & Persisted", `Master identity profile for ${fullName} successfully written to AES-256 encrypted vault!`, true, true);
      appendLog("VAULT", `Master profile updated: ${fullName} (AES-256-GCM AEAD encrypted)`);
    } catch (err) {
      showToast("Vault Encryption Error", err.message, false);
    } finally {
      if (saveProfileBtn) {
        saveProfileBtn.disabled = false;
        saveProfileBtn.innerHTML = `
          <svg class="w-3.5 h-3.5 text-void" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect width="18" height="11" x="3" y="11" rx="2" ry="2"/>
            <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
          </svg>
          <span>Save to Encrypted Vault</span>
        `;
      }
      if (saveProfileBtnBottom) saveProfileBtnBottom.disabled = false;
    }
  }

  if (saveProfileBtn) saveProfileBtn.addEventListener("click", saveProfile);
  if (saveProfileBtnBottom) saveProfileBtnBottom.addEventListener("click", saveProfile);

  // ---------------------------------------------------------------------------
  // Sample Profile & Clear Actions
  // ---------------------------------------------------------------------------
  const SAMPLE_PROFILE = {
    core: {
      full_name: "Arjun Sharma",
      email: "arjun.sharma@example.com",
      phone: "+919876543210",
      address_line1: "402 Palm Grove, Indiranagar",
      address_line2: "100 Feet Road",
      city: "Bengaluru",
      state_province: "Karnataka",
      postal_code: "560038",
      country: "India",
      citizenship: "India",
      date_of_birth: "1994-08-15",
    },
    tax: {
      tax_residence_country: "India",
      pan: "ABCDE1234F",
      ssn_itin: null,
      has_us_tax_id: false,
      tax_treaty_country: "India",
      tax_treaty_article: "Article 12(2)",
      treaty_withholding_rate: "15%",
      treaty_income_type: "Royalties / Independent Personal Services",
      claim_treaty_benefits: true,
    },
    career: {
      headline: "Senior Full-Stack & Distributed Systems Engineer",
      years_of_experience: 8,
      skills: ["Python", "FastAPI", "React", "TypeScript", "PostgreSQL", "Docker", "Kubernetes", "AWS"],
      resume_markdown: "# Arjun Sharma\n\nSenior Full-Stack Engineer with 8+ years developing distributed systems...\n\n## Experience\n- Staff Software Engineer at Acme Cloud (2021-Present)\n- Senior Systems Engineer at TechCorp (2018-2021)",
      github_url: "https://github.com/arjunsharma-dev",
      linkedin_url: "https://linkedin.com/in/arjunsharma-dev",
      portfolio_url: "https://arjunsharma.dev",
      work_history: "Staff Software Engineer at Acme Cloud (2021-Present): Architected multi-region event streaming pipeline.\nSenior Systems Engineer at TechCorp (2018-2021): Scaled core API services from 10k to 500k RPM.",
      education_degree: "Bachelor of Technology in Computer Science",
      education_university: "Indian Institute of Technology, Bombay",
      education_grad_year: "2016",
      education_gpa: "3.85 / 4.0",
      bio: "Passionate distributed systems engineer specializing in high-throughput backend services, resilient cloud architectures, and privacy-preserving automation.",
      custom_qa_pairs: {
        why_interested: "Excited by challenging high-scale distributed systems problems and collaborative culture.",
        work_authorization: "Authorized to work as an independent international contractor (B2B / W-8BEN).",
      },
    },
    financial: {
      bank_name: "HDFC Bank",
      account_number: "50100234567890",
      routing_ifsc: "HDFC0000240",
      swift_bic: "HDFCINBB",
      wise_recipient_id: "wise_recp_98765432",
    },
  };

  if (loadSampleBtn) {
    loadSampleBtn.addEventListener("click", () => {
      populateFormFields(SAMPLE_PROFILE);
      showToast("Sample Profile Loaded", "Indian tech contractor sample attributes populated. Click 'Save' to persist to vault.");
    });
  }

  if (clearProfileBtn) {
    clearProfileBtn.addEventListener("click", () => {
      if (confirm("Clear all profile fields to start from a blank slate?")) {
        populateFormFields({
          core: { full_name: "", email: "", phone: "", address_line1: "", city: "", state_province: "", postal_code: "", country: "", citizenship: "" },
          tax: { tax_residence_country: "", pan: "", tax_treaty_country: "", tax_treaty_article: "", treaty_withholding_rate: "", claim_treaty_benefits: false },
          career: { headline: "", years_of_experience: 0, skills: [], resume_markdown: "", bio: "", work_history: "", education_degree: "", education_university: "", education_grad_year: "", education_gpa: "" },
          financial: {},
        });
        showToast("Form Cleared", "Enter your candidate details and click 'Save to Encrypted Vault'.");
      }
    });
  }

  // ---------------------------------------------------------------------------
  // Resume File Upload (Server-Side Extraction with Client Fallback)
  // ---------------------------------------------------------------------------
  async function handleResumeUpload(file) {
    if (!file) return;

    const fileName = file.name;
    const fileExt = fileName.split(".").pop().toLowerCase();

    if (resumeUploadStatus) {
      resumeUploadStatus.textContent = `Processing ${fileName} (${(file.size / 1024).toFixed(1)} KB)...`;
    }

    // Try server-side parsing (supports .pdf, .txt, .md)
    try {
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch("/api/vault/resume", {
        method: "POST",
        body: formData,
      });

      if (res.ok) {
        const data = await res.json();
        if (data.text) {
          setVal("career-resume-markdown", data.text);
          const pageInfo = data.pages > 1 ? `, ${data.pages} pages` : "";
          if (resumeUploadStatus) {
            resumeUploadStatus.textContent = `Parsed: ${fileName} (${(data.size_bytes / 1024).toFixed(1)} KB${pageInfo})`;
          }
          showToast("Resume Parsed", `Extracted text from ${fileName} and loaded into editor.`, true);
          return;
        }
      }
    } catch (err) {
      console.warn("Backend resume extraction failed, falling back to client reader:", err);
    }

    // Fallback for plain text / markdown files
    if (fileExt === "txt" || fileExt === "md") {
      const reader = new FileReader();
      reader.onload = (evt) => {
        const content = evt.target.result;
        setVal("career-resume-markdown", content);
        if (resumeUploadStatus) {
          resumeUploadStatus.textContent = `Loaded: ${fileName} (${(file.size / 1024).toFixed(1)} KB)`;
        }
        showToast("Resume Imported", `Text extracted from ${fileName} and loaded into editor.`, true);
      };
      reader.readAsText(file);
    } else {
      if (resumeUploadStatus) {
        resumeUploadStatus.textContent = `Selected: ${fileName} (Attached)`;
      }
      showToast("File Attached", `Selected ${fileName}. Please confirm or paste markdown text below.`, false);
    }
  }

  if (resumeFileInput) {
    resumeFileInput.addEventListener("change", (e) => {
      const file = e.target.files && e.target.files[0];
      handleResumeUpload(file);
    });
  }

  if (resumeDropzone) {
    ["dragenter", "dragover"].forEach((eventName) => {
      resumeDropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        resumeDropzone.classList.add("border-frosted-lilac", "bg-cobalt-panel/40");
      });
    });

    ["dragleave", "drop"].forEach((eventName) => {
      resumeDropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        resumeDropzone.classList.remove("border-frosted-lilac", "bg-cobalt-panel/40");
      });
    });

    resumeDropzone.addEventListener("drop", (e) => {
      const dt = e.dataTransfer;
      const file = dt && dt.files && dt.files[0];
      if (file) {
        handleResumeUpload(file);
      }
    });
  }

  // ---------------------------------------------------------------------------
  // CIBA Consent Decision Submissions
  // ---------------------------------------------------------------------------
  async function submitConsentDecision(approved) {
    if (!currentActiveTaskId) return;

    if (cibaApproveBtn) cibaApproveBtn.disabled = true;
    if (cibaRejectBtn) cibaRejectBtn.disabled = true;
    if (modalApproveBtn) modalApproveBtn.disabled = true;
    if (modalRejectBtn) modalRejectBtn.disabled = true;

    if (cibaTimerBadge) {
      cibaTimerBadge.textContent = approved
        ? "Decision: Approved — Resuming Form Fill..."
        : "Decision: Denied — Halting Pipeline...";
      cibaTimerBadge.style.color = approved ? "var(--emerald-success)" : "var(--rose-danger)";
    }

    try {
      const response = await fetch(`/api/tasks/${currentActiveTaskId}/consent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approved }),
      });

      if (!response.ok) {
        throw new Error("Failed to record CIBA consent decision on backend");
      }

      appendLog(
        "CIBA",
        `Human-in-the-loop consent ${approved ? "GRANTED" : "REFUSED"} for task ${currentActiveTaskId}`
      );
      closeDiffModal();
    } catch (err) {
      appendLog("ERROR", `Consent submission error: ${err.message}`);
      if (cibaApproveBtn) cibaApproveBtn.disabled = false;
      if (cibaRejectBtn) cibaRejectBtn.disabled = false;
      if (modalApproveBtn) modalApproveBtn.disabled = false;
      if (modalRejectBtn) modalRejectBtn.disabled = false;
    }
  }

  if (cibaApproveBtn) cibaApproveBtn.addEventListener("click", () => submitConsentDecision(true));
  if (cibaRejectBtn) cibaRejectBtn.addEventListener("click", () => submitConsentDecision(false));
  if (modalApproveBtn) modalApproveBtn.addEventListener("click", () => submitConsentDecision(true));
  if (modalRejectBtn) modalRejectBtn.addEventListener("click", () => submitConsentDecision(false));

  // ---------------------------------------------------------------------------
  // Pipeline Stages
  // ---------------------------------------------------------------------------
  const stageElements = {
    SESSION_INIT: document.getElementById("stage-step-1"),
    DOM_EXTRACTION: document.getElementById("stage-step-2"),
    AI_REASONING: document.getElementById("stage-step-3"),
    CIBA_CONSENT: document.getElementById("stage-step-4"),
    FORM_FILLING: document.getElementById("stage-step-5"),
    COMPLETED: document.getElementById("stage-step-5"),
  };

  const stageOrder = [
    "SESSION_INIT",
    "DOM_EXTRACTION",
    "AI_REASONING",
    "CIBA_CONSENT",
    "FORM_FILLING",
    "COMPLETED",
  ];

  function resetStages() {
    Object.values(stageElements).forEach((el) => {
      if (el) el.classList.remove("active", "completed");
    });
    if (progressBar) {
      progressBar.style.width = "0%";
      progressBar.style.backgroundColor = "";
    }
    if (terminalLogs) terminalLogs.innerHTML = "";
    if (cibaConsentCard) cibaConsentCard.style.display = "none";
    if (replayLiveDot) replayLiveDot.style.display = "none";
  }

  function appendLog(stage, message, timestamp) {
    if (!terminalLogs) return;
    const timeStr = timestamp
      ? new Date(timestamp * 1000).toLocaleTimeString()
      : new Date().toLocaleTimeString();
    const logDiv = document.createElement("div");
    logDiv.className = "log-entry flex items-start gap-3 mb-1";
    logDiv.innerHTML = `
      <span class="log-time text-ash/50 shrink-0">[${timeStr}]</span>
      <span class="log-stage text-frosted-lilac shrink-0">&lt;${escapeHtml(stage)}&gt;</span>
      <span class="log-msg text-quartz">${escapeHtml(message)}</span>
    `;
    terminalLogs.appendChild(logDiv);
    terminalLogs.scrollTop = terminalLogs.scrollHeight;
  }

  function updatePipelineStage(stage, percentage) {
    if (progressBar) progressBar.style.width = `${percentage}%`;

    const currentIdx = stageOrder.indexOf(stage);
    stageOrder.forEach((st, idx) => {
      const el = stageElements[st];
      if (!el) return;
      if (idx < currentIdx) {
        el.classList.remove("active");
        el.classList.add("completed");
      } else if (idx === currentIdx) {
        el.classList.remove("completed");
        el.classList.add("active");
      } else {
        el.classList.remove("active", "completed");
      }
    });

    if (stage === "COMPLETED") {
      Object.values(stageElements).forEach((el) => {
        if (el) el.classList.add("completed");
      });
    }

    if (stage === "CIBA_CONSENT") {
      if (cibaConsentCard) {
        cibaConsentCard.style.display = "block";
        if (cibaApproveBtn) cibaApproveBtn.disabled = false;
        if (cibaRejectBtn) cibaRejectBtn.disabled = false;
      }
      if (modalApproveBtn) modalApproveBtn.style.display = "inline-flex";
      if (modalRejectBtn) modalRejectBtn.style.display = "inline-flex";
    }
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // ---------------------------------------------------------------------------
  // Target Form Execution Dispatch
  // ---------------------------------------------------------------------------
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const targetUrl = targetUrlInput ? targetUrlInput.value.trim() : "";
      const isDryRun = dryRunToggle ? dryRunToggle.checked : true;

      if (!targetUrl) {
        alert("Please enter a target form URL (ATS job or W-8BEN compliance form).");
        return;
      }

      resetStages();
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = "Processing Pipeline...";
      }
      if (statusText) {
        statusText.textContent = "Initiating cloud sandbox...";
        statusText.style.color = "var(--amber-primary)";
      }
      if (replayLiveDot) replayLiveDot.style.display = "inline-block";

      try {
        const response = await fetch("/api/fill", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: targetUrl, dry_run: isDryRun }),
        });

        if (!response.ok) {
          const errData = await response.json().catch(() => ({}));
          throw new Error(errData.detail || "Failed to start form filling task");
        }

        const data = await response.json();
        const taskId = data.task_id;
        currentActiveTaskId = taskId;
        appendLog("DISPATCH", `Task created: ${taskId} (dry_run=${isDryRun})`);

        connectTelemetryStream(taskId, isDryRun);
      } catch (err) {
        appendLog("ERROR", err.message);
        if (statusText) {
          statusText.textContent = `Error: ${err.message}`;
          statusText.style.color = "var(--rose-danger)";
        }
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = "Start Autonomous Fill";
        }
        if (replayLiveDot) replayLiveDot.style.display = "none";
      }
    });
  }

  function connectTelemetryStream(taskId, isDryRun) {
    currentActiveTaskId = taskId;
    if (activeEventSource) activeEventSource.close();
    if (replayLiveDot) replayLiveDot.style.display = "inline-block";

    const eventSource = new EventSource(`/api/tasks/${taskId}/events`);
    activeEventSource = eventSource;

    eventSource.onopen = () => {
      appendLog("SSE", `Live telemetry stream connected to /api/tasks/${taskId}/events`);
    };

    eventSource.onmessage = (e) => {
      try {
        const eventData = JSON.parse(e.data);
        const { stage, percentage, message, timestamp, result, error } = eventData;

        updatePipelineStage(stage, percentage);
        appendLog(stage, message, timestamp);

        if (eventData.diff) {
          populateDiffTable({ diff: eventData.diff });
        }

        if (statusText) {
          statusText.textContent = `${stage} (${percentage}%) — ${message}`;
        }

        if (stage === "COMPLETED") {
          eventSource.close();
          handleCompletion(taskId, result || {}, isDryRun);
        } else if (stage === "FAILED" || stage === "REFUSED") {
          eventSource.close();
          handleFailure(error || message, stage);
        }
      } catch (err) {
        console.error("SSE parse error:", err);
      }
    };

    eventSource.onerror = (err) => {
      console.warn("SSE connection closed or error:", err);
      fetch(`/api/tasks/${taskId}`)
        .then((res) => res.json())
        .then((task) => {
          if (task.status === "completed") {
            eventSource.close();
            handleCompletion(taskId, task.result || task || {}, isDryRun);
          } else if (task.status === "failed" || task.status === "refused") {
            eventSource.close();
            handleFailure(task.error || `Task halted with status: ${task.status}`, task.status.toUpperCase());
          }
        })
        .catch(() => {});
    };
  }

  function handleCompletion(taskId, result, isDryRun) {
    if (statusText) {
      statusText.textContent = isDryRun
        ? "DRY_RUN_SUCCESS — Halting safely before submission"
        : "SUBMITTED — Application filed successfully";
      statusText.style.color = "var(--emerald-success)";
    }

    if (progressBar) {
      progressBar.style.width = "100%";
      progressBar.style.backgroundColor = "var(--emerald-success)";
    }

    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = "Start Autonomous Fill";
    }

    if (replayLiveDot) replayLiveDot.style.display = "none";

    if (cibaConsentCard && cibaTimerBadge) {
      cibaTimerBadge.textContent = "Identity Released (RFC 9396 Approved)";
      cibaTimerBadge.style.color = "var(--emerald-success)";
    }

    const replayUrl =
      result.replay_url ||
      result.live_view_url ||
      `https://browserbase.com/sessions/${result.session_id || taskId}`;
    if (replayFrame) {
      replayFrame.src = replayUrl;
      replayFrame.style.display = "block";
    }
    const placeholder = document.getElementById("replay-placeholder");
    if (placeholder) placeholder.style.display = "none";

    const replayLink = document.getElementById("replay-external-link");
    if (replayLink) {
      replayLink.href = replayUrl;
      replayLink.textContent = "Open in Browserbase";
    }

    populateDiffTable(result);
  }

  function handleFailure(errorMessage, stage = "FAILED") {
    if (statusText) {
      statusText.textContent = `Execution Halted [${stage}]: ${errorMessage}`;
      statusText.style.color = stage === "REFUSED" ? "var(--amber-primary)" : "var(--rose-danger)";
    }
    if (progressBar) {
      progressBar.style.backgroundColor = stage === "REFUSED" ? "var(--amber-primary)" : "var(--rose-danger)";
    }
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = "Start Autonomous Fill";
    }
    if (replayLiveDot) replayLiveDot.style.display = "none";
    if (diffTbody && (!diffTbody.children.length || diffTbody.textContent.includes("Streaming"))) {
      diffTbody.innerHTML = `
        <tr>
          <td colspan="4" style="text-align: center; color: ${stage === 'REFUSED' ? 'var(--amber-primary)' : 'var(--rose-danger)'}; padding: 1.5rem;">
            Pipeline halted [${escapeHtml(stage)}]: ${escapeHtml(errorMessage)}
          </td>
        </tr>
      `;
    }
  }

  function populateDiffTable(result) {
    if (!diffTbody) return;
    diffTbody.innerHTML = "";

    let items = [];
    if (result && Array.isArray(result.diff)) {
      items = result.diff;
    } else if (result && result.diff && Array.isArray(result.diff.items)) {
      items = result.diff.items;
    } else if (result && Array.isArray(result.items)) {
      items = result.items;
    } else if (result && result.plan && Array.isArray(result.plan.items)) {
      items = result.plan.items;
    }

    if (!items || items.length === 0) {
      diffTbody.innerHTML = `
        <tr>
          <td colspan="4" class="p-6 text-center text-ash/60">
            No form field diff records available for this task.
          </td>
        </tr>
      `;
      return;
    }

    items.forEach((item) => {
      const tr = document.createElement("tr");
      tr.className = "border-b border-obsidian-edge/50 hover:bg-void/30 transition-colors";
      const fieldName = item.field || item.field_name || item.field_id || "Field";
      const tier = item.tier || "PUBLIC";
      const value = item.value !== undefined ? String(item.value) : (item.masked_value !== undefined ? String(item.masked_value) : "");
      const itemStatus = item.status || "Filled";

      const badgeClass =
        tier === "PUBLIC"
          ? "text-blue-public bg-blue-public/10 border-blue-public/30"
          : tier === "SEMI_SENSITIVE"
          ? "text-amber-primary bg-amber-primary/10 border-amber-primary/30"
          : tier === "CRITICAL_TAX"
          ? "text-purple-tax bg-purple-tax/10 border-purple-tax/30"
          : "text-rose-danger bg-rose-danger/10 border-rose-danger/30";

      const statusColor =
        itemStatus === "Filled" || itemStatus === "Uploaded" || itemStatus === "Selected"
          ? "text-emerald-success"
          : itemStatus === "Protected"
          ? "text-amber-primary"
          : "text-ash";

      tr.innerHTML = `
        <td class="p-3 font-medium text-quartz">${escapeHtml(fieldName)}</td>
        <td class="p-3"><span class="inline-block px-2 py-0.5 rounded-full border text-[10px] font-mono font-semibold ${badgeClass}">${escapeHtml(tier)}</span></td>
        <td class="p-3 font-mono text-ash">${escapeHtml(value)}</td>
        <td class="p-3"><span class="font-medium text-xs ${statusColor}">${escapeHtml(itemStatus)}</span></td>
      `;
      diffTbody.appendChild(tr);
    });

    const modalDiffContent = document.getElementById("modal-diff-content");
    if (modalDiffContent && items.length > 0) {
      modalDiffContent.innerHTML = `<pre style="font-family: var(--font-mono); font-size: 0.8rem; overflow-x: auto; background: var(--color-abyss); padding: 1.25rem; border-radius: 8px; border: 1px solid var(--color-inkline);">${escapeHtml(JSON.stringify(items, null, 2))}</pre>`;
    }
  }

  // ---------------------------------------------------------------------------
  // Auto-connect task if data-task-id is present (task_detail.html)
  // ---------------------------------------------------------------------------
  const pageTaskId =
    document.body.getAttribute("data-task-id") ||
    document.querySelector("[data-task-id]")?.getAttribute("data-task-id") ||
    (typeof currentTaskId !== "undefined" ? currentTaskId : null);
  if (pageTaskId) {
    currentActiveTaskId = pageTaskId;
    fetch(`/api/tasks/${pageTaskId}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((task) => {
        if (!task) return;
        if (task.status === "completed") {
          updatePipelineStage("COMPLETED", 100);
          handleCompletion(pageTaskId, task.result || task, true);
        } else if (task.status === "failed" || task.status === "refused") {
          handleFailure(task.error || `Task halted with status: ${task.status}`, task.status.toUpperCase());
        } else if (task.current_stage) {
          updatePipelineStage(task.current_stage, task.progress_percentage || 50);
          if (task.diff) populateDiffTable({ diff: task.diff });
        }
      })
      .catch(() => {});

    connectTelemetryStream(pageTaskId, true);
  }

  // Load profile on startup to populate displays & form cache
  loadProfileIntoForm();

  // Expose methods for testing
  window.connectTelemetryStream = connectTelemetryStream;
  window.populateDiffTable = populateDiffTable;
  window.submitConsentDecision = submitConsentDecision;
  window.loadProfileIntoForm = loadProfileIntoForm;
  window.saveProfile = saveProfile;
  window.switchTab = switchTab;
});
