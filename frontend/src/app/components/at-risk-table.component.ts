import { CommonModule } from '@angular/common';
import { Component, Input } from '@angular/core';
import { AtRiskRow } from '../models';

@Component({
  selector: 'app-at-risk-table',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="card full">
      <h2>Deliveries at risk ({{ rows.length }})</h2>
      <div style="overflow-x:auto">
        <table>
          <thead>
            <tr>
              <th>PO</th>
              <th>Supplier</th>
              <th>Part</th>
              <th>Carrier</th>
              <th>Status</th>
              <th class="num">Slip (h)</th>
              <th>Promised</th>
              <th>Risk</th>
            </tr>
          </thead>
          <tbody>
            <tr *ngFor="let r of rows">
              <td>{{ r.po_id }}</td>
              <td>{{ r.supplier_name }}</td>
              <td>{{ r.part_desc }}</td>
              <td>{{ r.carrier ?? '—' }}</td>
              <td>{{ r.delivery_status }}</td>
              <td class="num">{{ r.slip_hours ?? '—' }}</td>
              <td>{{ r.promised_delivery_ts }}</td>
              <td><span class="pill" [class]="'pill ' + r.risk_level">{{ r.risk_level }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  `,
})
export class AtRiskTableComponent {
  @Input({ required: true }) rows: AtRiskRow[] = [];
}
