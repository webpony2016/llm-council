import { useState, useEffect, useCallback } from 'react';
import { copilotApi } from '../copilotApi';
import './CopilotAuth.css';

/**
 * CopilotAuth component for GitHub Copilot authentication.
 * Displays authentication status and provides login/logout functionality.
 */
function CopilotAuth({ onStatusChange }) {
  const [status, setStatus] = useState({ authenticated: false, available_models: [] });
  const [authFlow, setAuthFlow] = useState(null); // { user_code, verification_uri, device_code }
  const [isPolling, setIsPolling] = useState(false);
  const [error, setError] = useState(null);

  // Check authentication status on mount
  useEffect(() => {
    checkStatus();
  }, []);

  // Notify parent of status changes
  useEffect(() => {
    if (onStatusChange) {
      onStatusChange(status);
    }
  }, [status, onStatusChange]);

  const checkStatus = async () => {
    try {
      const result = await copilotApi.getStatus();
      setStatus(result);
      setError(null);
    } catch (err) {
      setError('Failed to check Copilot status');
      console.error(err);
    }
  };

  const startAuth = async () => {
    try {
      setError(null);
      const result = await copilotApi.startAuth();
      setAuthFlow(result);
    } catch (err) {
      setError('Failed to start authentication');
      console.error(err);
    }
  };

  const pollForToken = async () => {
    if (!authFlow?.device_code) return;

    setIsPolling(true);
    setError(null);

    try {
      const result = await copilotApi.pollToken(authFlow.device_code);
      if (result.success) {
        setAuthFlow(null);
        await checkStatus();
      } else {
        setError(result.message || 'Authentication failed');
      }
    } catch (err) {
      setError('Authentication failed or timed out');
      console.error(err);
    } finally {
      setIsPolling(false);
    }
  };

  const handleLogout = async () => {
    try {
      await copilotApi.logout();
      setStatus({ authenticated: false, available_models: [] });
      setError(null);
    } catch (err) {
      setError('Failed to logout');
      console.error(err);
    }
  };

  const copyToClipboard = useCallback((text) => {
    navigator.clipboard.writeText(text);
  }, []);

  // Render authenticated state
  if (status.authenticated) {
    return (
      <div className="copilot-auth authenticated">
        <div className="status-indicator">
          <span className="status-dot success"></span>
          <span className="status-text">Copilot Connected</span>
        </div>
        <div className="model-count">
          {status.available_models.length} models available
        </div>
        <button className="logout-btn" onClick={handleLogout}>
          Disconnect
        </button>
      </div>
    );
  }

  // Render auth flow in progress
  if (authFlow) {
    return (
      <div className="copilot-auth auth-flow">
        <h3>Connect GitHub Copilot</h3>
        <div className="auth-steps">
          <div className="step">
            <span className="step-number">1</span>
            <span className="step-text">
              Copy this code:{' '}
              <code
                className="user-code"
                onClick={() => copyToClipboard(authFlow.user_code)}
                title="Click to copy"
              >
                {authFlow.user_code}
              </code>
            </span>
          </div>
          <div className="step">
            <span className="step-number">2</span>
            <span className="step-text">
              Open{' '}
              <a
                href={authFlow.verification_uri}
                target="_blank"
                rel="noopener noreferrer"
              >
                {authFlow.verification_uri}
              </a>
            </span>
          </div>
          <div className="step">
            <span className="step-number">3</span>
            <span className="step-text">Enter the code and authorize</span>
          </div>
          <div className="step">
            <span className="step-number">4</span>
            <span className="step-text">
              <button
                className="verify-btn"
                onClick={pollForToken}
                disabled={isPolling}
              >
                {isPolling ? 'Waiting for authorization...' : "I've authorized, verify"}
              </button>
            </span>
          </div>
        </div>
        {error && <div className="error-message">{error}</div>}
        <button className="cancel-btn" onClick={() => setAuthFlow(null)}>
          Cancel
        </button>
      </div>
    );
  }

  // Render unauthenticated state
  return (
    <div className="copilot-auth unauthenticated">
      <div className="status-indicator">
        <span className="status-dot"></span>
        <span className="status-text">Copilot Not Connected</span>
      </div>
      {error && <div className="error-message">{error}</div>}
      <button className="connect-btn" onClick={startAuth}>
        Connect GitHub Copilot
      </button>
    </div>
  );
}

export default CopilotAuth;
