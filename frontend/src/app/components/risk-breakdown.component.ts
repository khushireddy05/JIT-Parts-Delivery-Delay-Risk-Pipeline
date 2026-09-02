import { CommonModule } from '@angular/common';
import { Component, Input } from '@angular/core';
import { RiskBreakdownRow } from '../models';

const COLOR: Record<string, string> = {
  LOW: 'var(--low)',
  ON_TIME: 'var(--ontime)',
  MEDIUM: 'var(--medium)',
  HIGH: 'var(--high)',
  LATE: 'var(--late)',
};

@Component({
  selector: 'app-risk-breakdown',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="card">
      <h2>Delivery risk breakdown</h2>
      <div *ngFor="let row of rows" class="bar-row">
        <span class="bar-label">{{ row.risk_level }}</span>
        <span class="bar-track">
          <span
            class="bar-fill"
            [style.width.%]="pct(row.deliveries)"
            [style.background]="color(row.risk_level)"
          ></span>
        </span>
        <span class="bar-value">{{ row.deliveries }}</span>
      </div>
    </div>
  `,
})
export class RiskBreakdownComponent {
  @Input({ required: true }) rows: RiskBreakdownRow[] = [];

  private get max(): number {
    return this.rows.reduce((m, r) => Math.max(m, r.deliveries), 0) || 1;
  }

  pct(n: number): number {
    return (n / this.max) * 100;
  }

  color(level: string): string {
    return COLOR[level] ?? 'var(--muted)';
  }
}
