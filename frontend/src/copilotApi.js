/**
 * Copilot API extensions for authentication.
 */

const API_BASE = 'http://localhost:8001';

export const copilotApi = {
  /**
   * Get Copilot authentication status.
   */
  async getStatus() {
    const response = await fetch(`${API_BASE}/api/copilot/status`);
    if (!response.ok) {
      throw new Error('Failed to get Copilot status');
    }
    return response.json();
  },

  /**
   * Start Copilot OAuth device flow.
   * Returns device_code, user_code, and verification_uri.
   */
  async startAuth() {
    const response = await fetch(`${API_BASE}/api/copilot/auth`, {
      method: 'POST',
    });
    if (!response.ok) {
      throw new Error('Failed to start Copilot auth');
    }
    return response.json();
  },

  /**
   * Poll for Copilot access token after user authorizes.
   * This will wait until the user authorizes or timeout.
   */
  async pollToken(deviceCode) {
    const response = await fetch(`${API_BASE}/api/copilot/token`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ device_code: deviceCode }),
    });
    if (!response.ok) {
      throw new Error('Failed to poll for Copilot token');
    }
    return response.json();
  },

  /**
   * Logout from Copilot.
   */
  async logout() {
    const response = await fetch(`${API_BASE}/api/copilot/logout`, {
      method: 'POST',
    });
    if (!response.ok) {
      throw new Error('Failed to logout from Copilot');
    }
    return response.json();
  },

  /**
   * Get available providers.
   */
  async getProviders() {
    const response = await fetch(`${API_BASE}/api/providers`);
    if (!response.ok) {
      throw new Error('Failed to get providers');
    }
    return response.json();
  },

  /**
   * Get available models.
   */
  async getModels() {
    const response = await fetch(`${API_BASE}/api/models`);
    if (!response.ok) {
      throw new Error('Failed to get models');
    }
    return response.json();
  },

  /**
   * Get council configuration.
   */
  async getCouncilConfig() {
    const response = await fetch(`${API_BASE}/api/council/config`);
    if (!response.ok) {
      throw new Error('Failed to get council config');
    }
    return response.json();
  },
};
