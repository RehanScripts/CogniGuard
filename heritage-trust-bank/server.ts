/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import express from "express";
import path from "path";
import { createServer as createViteServer } from "vite";
import { LoginRequest, LoginResponse, StepUpVerifyRequest, StepUpVerifyResponse, ProfileOut, AccountOut, TransactionOut } from "./src/types";

async function startServer() {
  const app = express();
  const PORT = 3000;

  // Middleware to parse incoming JSON payloads
  app.use(express.json());

  // Memory store for active sessions and challenges
  const activeSessions = new Set<string>();
  const activeChallenges = new Map<string, { challenge_id: string; required_factors: string[] }>();

  // Initialize pre-seeded default session for direct or demo accessibility if needed
  activeSessions.add("session_token_steady_123");

  console.log("Express backend initializing routes...");

  // API Route: Authentication Login
  app.post("/api/v1/auth/login", (req, res) => {
    const { username, password, behavior } = req.body as LoginRequest;

    if (!username || !password) {
      res.status(400).json({
        action: "block",
        hardening: {
          action: "Login parameters invalid. Customer ID and Password must be supplied."
        },
        retry_after_s: 10
      });
      return;
    }

    // Default mock check - simple validation
    if (password === "wrongpass") {
      res.status(401).json({
        action: "block",
        hardening: {
          action: "Incorrect password credentials. Standard temporary delay penalty applied."
        },
        retry_after_s: 5
      });
      return;
    }

    // Heuristics based on CogniGuard behavior profile collected
    const cadence = behavior?.keystrokeCadence || "steady";

    if (cadence === "robotic") {
      // 1. Robotic keystroke pattern -> Immediate automated blocking
      res.json({
        action: "block",
        hardening: {
          action: "Device fingerprinted and transaction flow blocked. Cognitive biometrics flagged non-human keystroke cadence (robotic velocity)."
        },
        retry_after_s: 3600,
        trust_score: 12,
        behavior_match_score: 8
      } as LoginResponse);
    } else if (cadence === "erratic") {
      // 2. Erratic human speed or anomalous metrics -> Step-up verification
      const challengeId = "challenge_mfa_" + Math.random().toString(36).substring(2, 8);
      const challengeObj = {
        challenge_id: challengeId,
        required_factors: ["SMS OTP (Code: 123456)", "Biometric Fingerprint/FaceId Check"]
      };
      activeChallenges.set(challengeId, challengeObj);

      res.json({
        action: "verify",
        challenge: challengeObj,
        enrollment: "Security Profile Calibration: 6/10",
        trust_score: 54,
        behavior_match_score: 41
      } as LoginResponse);
    } else {
      // 3. Steady, normal human keystroke cadence -> Immediate seamless access
      const sessionToken = "session_token_steady_" + Math.random().toString(36).substring(2, 10);
      activeSessions.add(sessionToken);

      res.json({
        action: "allow",
        session_token: sessionToken,
        enrollment: "Security Profile Calibration: 10/10",
        trust_score: 96,
        behavior_match_score: 98
      } as LoginResponse);
    }
  });

  // API Route: Step-Up verification
  app.post("/api/v1/auth/step-up/verify", (req, res) => {
    const { challenge_id, otp_or_assertion } = req.body as StepUpVerifyRequest;

    // Check challenge existence
    if (!challenge_id) {
      res.status(404).json({ error: "Stale or unknown challenge. Routing back to authentication window." });
      return;
    }

    // Check if challenge is registered
    const challengeExists = activeChallenges.has(challenge_id);
    if (!challenge_id.startsWith("challenge_mfa_") && !challengeExists) {
      res.status(404).json({ error: "Stale or unknown challenge. Routing back to authentication window." });
      return;
    }

    // Demo OTP check or Biometric simulation
    if (otp_or_assertion === "123456" || otp_or_assertion === "biometric_assertion_success") {
      const stepUpToken = "session_token_stepup_" + Math.random().toString(36).substring(2, 10);
      activeSessions.add(stepUpToken);
      // Remove verified challenge
      activeChallenges.delete(challenge_id);

      res.json({
        action: "allow",
        session_token: stepUpToken
      });
    } else {
      res.status(401).json({ error: "Incorrect code, try again." });
    }
  });

  // Middleware helper to check Bearer Token
  const verifyTokenMiddleware = (req: express.Request, res: express.Response, next: express.NextFunction) => {
    const authHeader = req.headers.authorization;
    if (!authHeader || !authHeader.startsWith("Bearer ")) {
      res.status(401).json({ error: "Unauthorized. Missing authorization headers." });
      return;
    }
    const token = authHeader.split(" ")[1];
    if (activeSessions.has(token) || token === "valid_session_token_xyz" || token.startsWith("session_token_")) {
      next();
    } else {
      res.status(401).json({ error: "Unauthorized or stale banking session token." });
    }
  };

  // API Route: Profile details
  app.get("/api/v1/banking/profile", verifyTokenMiddleware, (req, res) => {
    const profile: ProfileOut = {
      full_name: "Vikram Sen",
      masked_email: "v******n@heritage.com",
      kyc_level: "KYC Tier-3 Premium Verified"
    };
    res.json(profile);
  });

  // API Route: Account list
  app.get("/api/v1/banking/accounts", verifyTokenMiddleware, (req, res) => {
    const accounts: AccountOut[] = [
      {
        masked_account_number: "XXXX XXXX 8821",
        balance: "₹4,28,450.00",
        status: "Active",
        type: "Savings Account",
        detail: "Available Balance"
      },
      {
        masked_account_number: "**** **** **** 4092",
        balance: "₹12,480.50",
        status: "Active",
        type: "Heritage Platinum Visa",
        detail: "Outstanding Dues",
        due_date: "15 June 2024"
      }
    ];
    res.json(accounts);
  });

  // API Route: Recent Transactions list
  app.get("/api/v1/banking/transactions", verifyTokenMiddleware, (req, res) => {
    const limit = parseInt(req.query.limit as string) || 10;
    const allTransactions: TransactionOut[] = [
      {
        date: "24 May 2024",
        description: "Amazon India - Order #991",
        type: "Debit Card Payment",
        amount: "- ₹2,450.00",
        is_credit: false
      },
      {
        date: "22 May 2024",
        description: "Salary Credit - ABC Tech Corp",
        type: "NEFT Transfer",
        amount: "+ ₹1,85,000.00",
        is_credit: true
      },
      {
        date: "20 May 2024",
        description: "Zomato Media Pvt Ltd",
        type: "UPI Transfer",
        amount: "- ₹840.00",
        is_credit: false
      },
      {
        date: "18 May 2024",
        description: "Tata Power Mumbai",
        type: "Bill Payment",
        amount: "- ₹3,210.00",
        is_credit: false
      },
      {
        date: "15 May 2024",
        description: "Cash Deposit - ATM 4022",
        type: "Self Deposit",
        amount: "+ ₹15,000.00",
        is_credit: true
      },
      {
        date: "12 May 2024",
        description: "Netflix India Subscription",
        type: "Standing Instruction",
        amount: "- ₹649.00",
        is_credit: false
      },
      {
        date: "10 May 2024",
        description: "Swiggy Food Order",
        type: "UPI Transfer",
        amount: "- ₹412.00",
        is_credit: false
      },
      {
        date: "08 May 2024",
        description: "Transfer from Father - Pocket Money",
        type: "IMPS Transfer",
        amount: "+ ₹10,000.00",
        is_credit: true
      }
    ];

    res.json(allTransactions.slice(0, limit));
  });

  // Vite middleware for assets serving in development
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
    console.log("Vite dev middleware mounted successfully.");
  } else {
    const distPath = path.join(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*", (req, res) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
    console.log("Serving compiled production assets from /dist.");
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`Heritage Digital Banking server boot complete on http://0.0.0.0:${PORT}`);
  });
}

startServer().catch((err) => {
  console.error("FATAL: Failed to boot Express + Vite server:", err);
});
