import React from "react";
import { mount } from "enzyme";
import BetaBadge from "./BetaBadge";
import { clientConfig } from "@/services/auth";

/*
  Which features are beta is decided in `sqldesk/features.py` and arrives on
  `grantableFeatures`. The badge asks rather than carrying its own list, so
  the thing worth holding up is that it stops drawing the moment the flag
  moves — a page still saying "beta" about something that left beta two
  releases ago is worse than no badge at all.
*/
function withFeatures(features) {
  clientConfig.grantableFeatures = features;
}

describe("the beta badge", () => {
  afterEach(() => withFeatures([]));

  it("marks a feature the server calls beta", () => {
    withFeatures([{ name: "use_notebooks", label: "Use notebooks", beta: true }]);

    expect(mount(<BetaBadge feature="use_notebooks" />).find('[data-test="BetaBadge"]').exists()).toBe(true);
  });

  it("says nothing about a feature that is not", () => {
    withFeatures([{ name: "use_streams", label: "Use streams", beta: false }]);

    expect(mount(<BetaBadge feature="use_streams" />).isEmptyRender()).toBe(true);
  });

  it("says nothing when the install has never heard of the feature", () => {
    withFeatures([{ name: "use_streams", beta: true }]);

    expect(mount(<BetaBadge feature="use_notebooks" />).isEmptyRender()).toBe(true);
  });

  it("says nothing before the config has loaded, rather than throwing", () => {
    delete clientConfig.grantableFeatures;

    expect(mount(<BetaBadge feature="use_notebooks" />).isEmptyRender()).toBe(true);
  });
});
