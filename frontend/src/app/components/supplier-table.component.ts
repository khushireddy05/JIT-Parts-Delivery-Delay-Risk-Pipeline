import { CommonModule } from '@angular/common';
import { Component, Input } from '@angular/core';
import { SupplierOnTimeRow } from '../models';

@Component({
  selector: 'app-supplier-table',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="card">
      <h2>Supplier on-time rate</h2>
      <div *ngFor="let row of rows" class="bar-row">
        <span class="bar-label" [title]="row.supplier_name">{{ row.supplier_name }}</span>
        <span class="bar-track">
          <span
            class="bar-fill"
            [style.width.%]="row.on_time_rate * 100"
            [style.background]="row.on_time_rate < 0.85 ? 'var(--late)' : 'var(--low)'"
          ></span>
        </span>
        <span class="bar-value">
          {{ row.on_time_rate * 100 | number: '1.0-1' }}%
        </span>
      </div>
      <p class="state">Flagged below 85%. n = total deliveries per supplier.</p>
    </div>
  `,
})
export class SupplierTableComponent {
  @Input({ required: true }) rows: SupplierOnTimeRow[] = [];
}
