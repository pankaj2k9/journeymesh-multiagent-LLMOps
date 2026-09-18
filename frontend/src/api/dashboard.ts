import type { DashboardResponse } from '../types';
import { request } from './client';

export function getDashboard(): Promise<DashboardResponse> {
  return request<DashboardResponse>('/me/dashboard');
}
