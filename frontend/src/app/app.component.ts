import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { catchError, forkJoin, of } from 'rxjs';
import { AtRiskTableComponent } from './components/at-risk-table.component';
import { RiskBreakdownComponent } from './components/risk-breakdown.component';
import { SupplierTableComponent } from './components/supplier-table.component';
import { AtRiskRow, RiskBreakdownRow, SupplierOnTimeRow } from './models';
import { RiskService } from './risk.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    CommonModule,
    RiskBreakdownComponent,
    SupplierTableComponent,
    AtRiskTableComponent,
  ],
  template: `
    <div class="wrap">
      <h1>JIT Parts — Delay-Risk Dashboard</h1>
      <p class="sub">
        Inbound automotive parts deliveries scored for risk of arriving late to the line.
      </p>

      <p *ngIf="loading" class="state">Loading…</p>
      <p *ngIf="error" class="state err">{{ error }}</p>

      <div class="grid" *ngIf="!loading && !error">
        <app-risk-breakdown [rows]="breakdown" />
        <app-supplier-table [rows]="suppliers" />
        <app-at-risk-table [rows]="atRisk" />
      </div>
    </div>
  `,
})
export class AppComponent implements OnInit {
  loading = true;
  error = '';
  breakdown: RiskBreakdownRow[] = [];
  suppliers: SupplierOnTimeRow[] = [];
  atRisk: AtRiskRow[] = [];

  constructor(private readonly risk: RiskService) {}

  ngOnInit(): void {
    forkJoin({
      breakdown: this.risk.riskBreakdown(),
      suppliers: this.risk.supplierOnTime(),
      atRisk: this.risk.atRisk(100),
    })
      .pipe(catchError(() => of(null)))
      .subscribe((res) => {
        this.loading = false;
        if (!res) {
          this.error =
            'Could not reach the API. Start it with: uvicorn api.app:app --port 8000';
          return;
        }
        this.breakdown = res.breakdown;
        this.suppliers = res.suppliers;
        this.atRisk = res.atRisk;
      });
  }
}
