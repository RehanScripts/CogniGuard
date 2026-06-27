/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

export interface CogniGuardBehavior {
  profileName: string;
  keystrokeCadence: "steady" | "erratic" | "robotic";
  deviceFingerprint: string;
  locationMatched: boolean;
  mousePathAnomalies: boolean;
}

export interface LoginRequest {
  username?: string;
  password?: string;
  behavior?: CogniGuardBehavior;
}

export interface StepUpChallenge {
  challenge_id: string;
  required_factors: string[];
}

export interface LoginResponse {
  action: "allow" | "verify" | "block";
  session_token?: string;
  challenge?: StepUpChallenge;
  hardening?: {
    action: string;
  };
  retry_after_s?: number;
  enrollment?: string;
  trust_score?: number;
  behavior_match_score?: number;
}

export interface StepUpVerifyRequest {
  challenge_id: string;
  otp_or_assertion: string;
}

export interface StepUpVerifyResponse {
  action: "allow" | "deny";
  session_token?: string;
}

export interface ProfileOut {
  full_name: string;
  masked_email: string;
  kyc_level: string;
}

export interface AccountOut {
  masked_account_number: string;
  balance: string;
  status: string;
  type: string;
  detail: string;
  due_date?: string;
}

export interface TransactionOut {
  date: string;
  description: string;
  type: string;
  amount: string;
  is_credit: boolean;
}
