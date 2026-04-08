"""Lifting-line helper functions."""

import numpy as np


def LLCirc(N, theta, alpha, alpha_0, c, b, V_inf):
    """Solve lifting-line circulation coefficients using a sine-series method."""
    if isinstance(alpha, np.ndarray) == 1:
        if len(alpha) == 1:
            alpha = alpha * np.ones(N)
    else:
        alpha = alpha * np.ones(N)

    if isinstance(alpha_0, np.ndarray) == 1:
        if len(alpha_0) == 1:
            alpha_0 = alpha_0 * np.ones(N)
    else:
        alpha_0 = alpha_0 * np.ones(N)

    if isinstance(c, np.ndarray) == 1:
        if len(c) == 1:
            c = c * np.ones(N)
    else:
        c = c * np.ones(N)

    alpha = alpha * np.pi / 180.0
    alpha_0 = alpha_0 * np.pi / 180.0
    theta = theta * np.pi / 180.0

    C = np.zeros((N, N))
    B = np.zeros(N)

    for j in np.arange(0, N):
        for n in np.arange(0, N):
            C[j, n] = (2 * b / (np.pi * c[j])) * np.sin((n + 1) * theta[j]) + (
                (n + 1) * np.sin((n + 1) * theta[j]) / np.sin(theta[j])
            )
        B[j] = alpha[j] - alpha_0[j]

    A = np.linalg.solve(C, B)
    gamma = np.zeros(N)
    alpha_i = np.zeros(N)

    for j in np.arange(0, N):
        for n in np.arange(0, N):
            gamma[j] = gamma[j] + 2 * b * V_inf * A[n] * np.sin((n + 1) * theta[j])
            alpha_i[j] = alpha_i[j] + (n + 1) * A[n] * np.sin((n + 1) * theta[j]) / np.sin(theta[j])

    if A[0] == 0:
        d = 0
    else:
        d = 0.0
        for j in np.arange(2, N):
            d = d + j * (A[j - 1] / A[0]) ** 2
    e = 1 / (1 + d)

    return A, gamma, alpha_i, e

__all__ = ["LLCirc"]
