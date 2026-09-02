import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../environments/environment';
import { AtRiskRow, RiskBreakdownRow, SupplierOnTimeRow } from './models';

@Injectable({ providedIn: 'root' })
export class RiskService {
  private readonly base = environment.apiBaseUrl;

  constructor(private readonly http: HttpClient) {}

  riskBreakdown(): Observable<RiskBreakdownRow[]> {
    return this.http.get<RiskBreakdownRow[]>(`${this.base}/api/risk-breakdown`);
  }

  supplierOnTime(): Observable<SupplierOnTimeRow[]> {
    return this.http.get<SupplierOnTimeRow[]>(`${this.base}/api/supplier-on-time`);
  }

  atRisk(limit = 50): Observable<AtRiskRow[]> {
    return this.http.get<AtRiskRow[]>(`${this.base}/api/at-risk?limit=${limit}`);
  }
}
