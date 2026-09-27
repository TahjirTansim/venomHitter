#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inline GraphQL documents for the Shopify checkout engine.

These target /checkouts/unstable/graphql, which accepts full inline
queries — no JS bundle scraping needed, unlike the persisted-query
endpoint. Four documents:

  QUERY_PROPOSAL_SHIPPING  — first negotiation, bootstraps the session
  QUERY_PROPOSAL_DELIVERY  — second negotiation, commits delivery info
  MUTATION_SUBMIT          — submit card for completion
  QUERY_POLL               — poll receipt until charged/failed/3ds
"""

QUERY_PROPOSAL_SHIPPING = """
query Proposal($sessionInput: SessionTokenInput!, $queueToken: String) {
  session(sessionInput: $sessionInput) {
    negotiate(input: {
      purchaseProposal: {},
      checkpointData: null,
      queueToken: $queueToken,
      changesetTokens: null
    }) {
      __typename
      result {
        ... on NegotiationResultAvailable {
          checkpointData
          queueToken
          buyerProposal { __typename }
          sellerProposal { __typename }
          __typename
        }
        ... on CheckpointDenied   { redirectUrl __typename }
        ... on Throttled          { pollAfter queueToken pollUrl __typename }
        ... on NegotiationResultFailed { __typename }
        __typename
      }
      errors {
        code
        localizedMessage
        nonLocalizedMessage
        localizedMessageHtml
        __typename
      }
      __typename
    }
  }
}
"""

QUERY_PROPOSAL_DELIVERY = """
query Proposal($sessionInput: SessionTokenInput!, $queueToken: String) {
  session(sessionInput: $sessionInput) {
    negotiate(input: {
      purchaseProposal: {},
      checkpointData: null,
      queueToken: $queueToken,
      changesetTokens: null
    }) {
      __typename
      result {
        ... on NegotiationResultAvailable {
          checkpointData
          queueToken
          buyerProposal { __typename }
          sellerProposal { __typename }
          __typename
        }
        ... on CheckpointDenied   { redirectUrl __typename }
        ... on Throttled          { pollAfter queueToken pollUrl __typename }
        ... on NegotiationResultFailed { __typename }
        __typename
      }
      errors {
        code
        localizedMessage
        nonLocalizedMessage
        localizedMessageHtml
        __typename
      }
      __typename
    }
  }
}
"""

MUTATION_SUBMIT = """
mutation SubmitForCompletion(
  $input: NegotiationInput!,
  $attemptToken: String!,
  $metafields: [MetafieldInput!],
  $analytics: AnalyticsInput
) {
  submitForCompletion(
    input: $input,
    attemptToken: $attemptToken,
    metafields: $metafields,
    analytics: $analytics
  ) {
    ... on SubmitSuccess          { receipt { id token __typename } __typename }
    ... on SubmitAlreadyAccepted  { receipt { id token __typename } __typename }
    ... on SubmitFailed           { reason __typename }
    ... on SubmitRejected {
      errors {
        code
        localizedMessage
        nonLocalizedMessage
        __typename
      }
      __typename
    }
    ... on Throttled              { pollAfter pollUrl queueToken __typename }
    ... on CheckpointDenied       { redirectUrl __typename }
    ... on SubmittedForCompletion { receipt { id token __typename } __typename }
    __typename
  }
}
"""

QUERY_POLL = """
query PollForReceipt($receiptId: ID!, $sessionToken: String!) {
  receipt(
    receiptId: $receiptId,
    sessionInput: { sessionToken: $sessionToken }
  ) {
    ... on ProcessedReceipt {
      id
      token
      redirectUrl
      confirmationPage { url shouldRedirect __typename }
      orderStatusPageUrl
      __typename
    }
    ... on ProcessingReceipt { id pollDelay __typename }
    ... on WaitingReceipt    { id pollDelay __typename }
    ... on ActionRequiredReceipt {
      id
      action {
        ... on CompletePaymentChallenge   { offsiteRedirect url __typename }
        ... on CompletePaymentChallengeV2 { challengeType challengeData __typename }
        __typename
      }
      timeout { millisecondsRemaining __typename }
      __typename
    }
    ... on FailedReceipt {
      id
      processingError {
        ... on PaymentFailed                { code messageUntranslated hasOffsitePaymentMethod __typename }
        ... on InventoryReservationFailure  { __typename }
        ... on InventoryClaimFailure        { __typename }
        ... on OrderCreationFailure         { paymentsHaveBeenReverted __typename }
        ... on OrderCreationSchedulingFailure { __typename }
        ... on DiscountUsageLimitExceededFailure { __typename }
        ... on CustomerPersistenceFailure   { __typename }
        __typename
      }
      __typename
    }
    __typename
  }
}
"""
