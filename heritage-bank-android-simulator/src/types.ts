export type AndroidActivity =
  | 'LoginActivity'
  | 'DashboardActivity'
  | 'TransferActivity'
  | 'TransferSuccessActivity'
  | 'SecurityCenterActivity'
  | 'TransactionHistoryActivity';

export interface Beneficiary {
  id: string;
  name: string;
  vpa: string;
  avatar: string;
  initials: string;
}

export interface Transaction {
  id: string;
  beneficiary: string;
  category: 'food' | 'utilities' | 'transfer' | 'other';
  amount: number;
  timestamp: string;
  type: 'debit' | 'credit';
  status: 'success' | 'pending' | 'failed';
  paymentMethod: string;
  remarks?: string;
}

export interface Account {
  id: string;
  type: string;
  accountNo: string;
  balance: number;
  currency: string;
}

export interface BehaviorMetrics {
  typingSpeed: number; // characters per min
  flightTimeVariance: number; // ms
  holdTime: number; // ms
  tremorFreq: number; // Hz
  deviceAngle: number; // degrees
  aeReconError: number; // TFLite Reconstruction Error (0.0 to 10.0)
  activeCall: boolean; // Coercion trigger
}

export interface SecurityScores {
  trustScore: number; // 0.0 to 1.0
  behaviorMatchScore: number; // 0.0 to 1.0
  deviceTrust: number; // 0.0 to 1.0
  qualitativeState: 'Protected' | 'Needs attention' | 'Highly Protected';
}

export interface ClientBehaviorPayload {
  source: 'mobile_edge';
  derived_features: {
    typing_speed: number;
    flight_time_var: number;
    tremor_index: number;
    screen_pressure_avg: number;
  };
  ae_recon_error: number; // Populated from TFLite autoencoder
}

export interface ClientRequest {
  endpoint: string;
  method: string;
  payload: any;
  timestamp: string;
}

export interface ClientResponse {
  status: number;
  payload: {
    action: 'allow' | 'verify' | 'deny';
    trust_score: number;
    behavior_match_score: number;
    device_trust: number;
    txn_controls?: {
      coercion_warning_required: boolean;
      manual_approval_required: boolean;
      coercion_type?: 'active_call' | 'high_pressure';
      limit_coercion_amount?: number;
    };
    error_message?: string;
  };
  timestamp: string;
}

export interface ConsoleLogEntry {
  id: string;
  timestamp: string;
  tag: 'CogniGuardClient' | 'TFLiteModel' | 'Activity' | 'NetworkGateway';
  message: string;
  level: 'info' | 'warning' | 'error' | 'success';
}
