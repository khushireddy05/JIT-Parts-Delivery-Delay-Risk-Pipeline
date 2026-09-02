export interface RiskBreakdownRow {
  risk_level: 'LOW' | 'ON_TIME' | 'MEDIUM' | 'HIGH' | 'LATE';
  deliveries: number;
}

export interface SupplierOnTimeRow {
  supplier_name: string;
  total: number;
  at_risk: number;
  on_time_rate: number;
}

export interface AtRiskRow {
  po_id: string;
  supplier_name: string;
  part_desc: string;
  carrier: string | null;
  delivery_status: string;
  slip_hours: number | null;
  promised_delivery_ts: string;
  risk_level: 'MEDIUM' | 'HIGH' | 'LATE';
}
