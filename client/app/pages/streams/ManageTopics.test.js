import React from "react";
import { mount } from "enzyme";

import ManageTopics, { readingFormat, readingSettings } from "./ManageTopics";
import { axios } from "@/services/axios";

/*
  Enabling a topic is the access decision on a Kafka cluster, so the page's job
  is to make somebody look before they make it. The three numbers that cannot
  be guessed from a topic's name are what the messages contain, how fast they
  arrive, and what that buys -- and the two warnings are the ones that turn
  into a bad afternoon if nobody reads them.
*/
const CLUSTER = { id: 7, name: "Kafka", streams_only: true };
const WAREHOUSE = { id: 8, name: "Warehouse", streams_only: false };

function listing(topics) {
  return (url) => {
    if (url === "api/data_sources") {
      return Promise.resolve([CLUSTER, WAREHOUSE]);
    }
    return Promise.resolve({ topics });
  };
}

/*
  The page loads in two steps -- the clusters, then that cluster's topics --
  and each is a promise plus a render, so one flush is not enough to see the
  second. Several small ones rather than a timer: the test should not be slower
  than the thing it is testing.
*/
async function settle(wrapper, times = 4) {
  for (let index = 0; index < times; index += 1) {
    // A macrotask rather than a microtask: `.then().finally()` chains and the
    // renders between them do not all drain on one flush of the microtask
    // queue, and a test that half-loads the page asserts on half a page.
    // eslint-disable-next-line no-await-in-loop
    await new Promise((resolve) => setTimeout(resolve, 0));
    wrapper.update();
  }
}

async function render(topics) {
  jest.spyOn(axios, "get").mockImplementation(listing(topics));
  const wrapper = mount(<ManageTopics />);
  await settle(wrapper);
  return wrapper;
}

const analysis = {
  topic: "orders",
  read: 500,
  malformed: 0,
  columns: [{ name: "id", type: "integer" }],
  events_per_second: 12.5,
  window_seconds: 600,
  row_budget: 5000000,
  ceiling: 5000,
  sampled: false,
  sample_rate: 1,
};

describe("the Manage topics page", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("it lists the cluster's topics and marks the enabled ones", async () => {
    const wrapper = await render([
      { name: "orders", partitions: 3, enabled: true, columns: 4 },
      { name: "payments", partitions: 1, enabled: false, columns: 0 },
    ]);

    expect(wrapper.text()).toContain("orders");
    expect(wrapper.text()).toContain("payments");
    expect(wrapper.text()).toContain("enabled");
  });

  test("only Kafka clusters are offered, not every data source", async () => {
    const wrapper = await render([]);

    expect(wrapper.text()).not.toContain("Warehouse");
  });

  test("with no clusters at all it says who adds one", async () => {
    jest.spyOn(axios, "get").mockResolvedValue([WAREHOUSE]);
    const wrapper = mount(<ManageTopics />);
    await settle(wrapper);

    expect(wrapper.text()).toContain("No Kafka clusters yet");
  });

  test("analysing one shows what is in it and what that buys", async () => {
    const wrapper = await render([{ name: "orders", partitions: 1, enabled: false, columns: 0 }]);
    jest.spyOn(axios, "post").mockResolvedValue(analysis);

    wrapper.find('[data-test="AnalyseTopic"]').first().simulate("click");
    await settle(wrapper);

    const shown = wrapper.text();
    expect(shown).toContain("500");
    expect(shown).toContain("12.5");
    expect(shown).toContain("10 minutes");
    expect(shown).toContain("id");
  });

  test("messages that could not be parsed are a warning, not a footnote", async () => {
    // A schema inferred from a tenth of the messages is a trap.
    const wrapper = await render([{ name: "orders", partitions: 1, enabled: false, columns: 0 }]);
    jest.spyOn(axios, "post").mockResolvedValue({ ...analysis, malformed: 120 });

    wrapper.find('[data-test="AnalyseTopic"]').first().simulate("click");
    await settle(wrapper);

    expect(wrapper.text()).toContain("120 of 500 messages could not be read");
  });

  test("and so is a topic that would be sampled", async () => {
    const wrapper = await render([{ name: "orders", partitions: 1, enabled: false, columns: 0 }]);
    jest.spyOn(axios, "post").mockResolvedValue({ ...analysis, sampled: true, sample_rate: 8 });

    wrapper.find('[data-test="AnalyseTopic"]').first().simulate("click");
    await settle(wrapper);

    expect(wrapper.text()).toContain("1 event in 8 would be kept");
  });

  test("the schema lists every column, one per line, and the one SQLDesk adds", async () => {
    // A row of tags wrapped into an unreadable block past about eight fields,
    // and a topic with forty is ordinary.
    const wrapper = await render([{ name: "orders", partitions: 1, enabled: false, columns: 0 }]);
    const many = Array.from({ length: 24 }, (unused, index) => ({ name: `field_${index}`, type: "string" }));
    jest.spyOn(axios, "post").mockResolvedValue({ ...analysis, columns: many });

    wrapper.find('[data-test="AnalyseTopic"]').first().simulate("click");
    await settle(wrapper);

    const schema = wrapper.find('[data-test="TopicSchema"]').first();
    expect(schema.find(".streams-schema-row").length).toBe(25);
    expect(schema.text()).toContain("field_23");
    expect(schema.text()).toContain("_received_at");
  });

  test("a reading says when it was taken and offers to take another", async () => {
    // Without the time on it the figure reads as something precomputed, and
    // nobody thinks to take it again after the topic has changed.
    const wrapper = await render([{ name: "orders", partitions: 1, enabled: false, columns: 0 }]);
    const post = jest.spyOn(axios, "post").mockResolvedValue(analysis);

    wrapper.find('[data-test="AnalyseTopic"]').first().simulate("click");
    await settle(wrapper);
    expect(wrapper.text()).toContain("measured");

    wrapper.find('[data-test="AnalyseAgain"]').first().simulate("click");
    await settle(wrapper);

    expect(post).toHaveBeenCalledTimes(2);
  });

  test("an already-enabled topic is not offered the button that enables it", async () => {
    const wrapper = await render([{ name: "orders", partitions: 1, enabled: true, columns: 4 }]);
    jest.spyOn(axios, "post").mockResolvedValue(analysis);

    wrapper.find('[data-test="AnalyseTopic"]').first().simulate("click");
    await settle(wrapper);

    expect(wrapper.find('[data-test="EnableTopic"]').length).toBe(0);
  });

  test("sampling is explained whether or not it is happening", async () => {
    const wrapper = await render([{ name: "orders", partitions: 1, enabled: false, columns: 0 }]);
    jest.spyOn(axios, "post").mockResolvedValue(analysis);

    wrapper.find('[data-test="AnalyseTopic"]').first().simulate("click");
    await settle(wrapper);

    expect(wrapper.text()).toContain("Everything is kept");
    expect(wrapper.text()).toContain("5,000");
  });

  test("a cluster that will not answer says so instead of showing nothing", async () => {
    jest.spyOn(axios, "get").mockImplementation((url) => {
      if (url === "api/data_sources") {
        return Promise.resolve([CLUSTER]);
      }
      return Promise.reject({ message: "no route to host" });
    });
    const wrapper = mount(<ManageTopics />);
    await settle(wrapper);

    expect(wrapper.text()).toContain("no route to host");
  });
});

/*
  How a topic is read.

  Lag monitoring alarmed on SQLDesk because every stream joined a consumer group
  it never committed under. The default is now no group the broker can see, and
  the page has to say that in words -- an empty box alone reads as "not set yet",
  not as "deliberately invisible".
*/
describe("how a topic is read", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  async function analysed(topic) {
    const wrapper = await render([{ name: "orders", partitions: 3, enabled: false, columns: 0, ...topic }]);
    jest
      .spyOn(axios, "post")
      .mockImplementation((url) => (url.endsWith("/analyse") ? Promise.resolve(analysis) : Promise.resolve({})));
    wrapper.find('[data-test="AnalyseTopic"]').first().simulate("click");
    await settle(wrapper);
    return wrapper;
  }

  test("by default it says plainly that no group is joined and nothing is saved", async () => {
    const wrapper = await analysed({});

    expect(wrapper.find('[data-test="ConsumerGroupMeaning"]').text()).toContain("broker never sees one");
    expect(wrapper.find('[data-test="SavePositionMeaning"]').text()).toContain("Nothing is saved");
    expect(wrapper.find(".ant-checkbox-input").first().prop("disabled")).toBe(true);
  });

  test("a name says which group the broker will see, and makes saving possible", async () => {
    const wrapper = await analysed({});

    wrapper.find('input[data-test="ConsumerGroup"]').simulate("change", { target: { value: "analytics-sqldesk" } });
    await settle(wrapper, 1);

    expect(wrapper.find('[data-test="ConsumerGroupMeaning"]').text()).toContain('"analytics-sqldesk"');
    expect(wrapper.find(".ant-checkbox-input").first().prop("disabled")).toBe(false);
  });

  test("enabling sends how it should read", async () => {
    const wrapper = await analysed({});

    wrapper.find('input[data-test="ConsumerGroup"]').simulate("change", { target: { value: "  analytics-sqldesk  " } });
    await settle(wrapper, 1);
    wrapper.find('button[data-test="EnableTopic"]').simulate("click");
    await settle(wrapper, 1);

    const enabling = axios.post.mock.calls.find(([url]) => url.endsWith("/topics/orders"));
    expect(enabling[1]).toEqual({
      consumer_group: "analytics-sqldesk",
      save_position: false,
      start_from: "latest",
      value_format: "auto",
    });
  });

  test("an enabled topic shows what it is set to and offers to save a change", async () => {
    const wrapper = await analysed({
      enabled: true,
      consumer_group: "analytics-sqldesk",
      save_position: true,
      start_from: "saved",
    });

    expect(wrapper.find('input[data-test="ConsumerGroup"]').prop("value")).toBe("analytics-sqldesk");
    expect(wrapper.find('[data-test="SavePositionMeaning"]').text()).toContain("resumes where it stopped");
    expect(wrapper.find('button[data-test="SaveHowItReads"]').exists()).toBe(true);
    expect(wrapper.find('button[data-test="EnableTopic"]').exists()).toBe(false);
  });

  test("starting from the beginning carries a warning about what it costs", async () => {
    const wrapper = await analysed({ start_from: "earliest" });

    expect(wrapper.find('[data-test="EarliestWarning"]').exists()).toBe(true);
  });
});

/*
  Avro and Protobuf. Automatic needs nothing; the other two need a schema file,
  checked by the server the moment it is uploaded, so a typo in a .proto is a
  sentence under the upload rather than a consumer that stops later.
*/
describe("what a topic's messages are", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  const PROTO = 'syntax = "proto3";\nmessage Payment { int64 id = 1; }\n';

  async function analysed(topic, checked) {
    const wrapper = await render([{ name: "payments", partitions: 1, enabled: false, columns: 0, ...topic }]);
    jest.spyOn(axios, "post").mockImplementation((url) => {
      if (url.endsWith("/analyse")) {
        return Promise.resolve({ ...analysis, topic: "payments" });
      }
      if (url.endsWith("/stream_schema")) {
        return checked;
      }
      return Promise.resolve({});
    });
    wrapper.find('[data-test="AnalyseTopic"]').first().simulate("click");
    await settle(wrapper);
    return wrapper;
  }

  function chooseFormat(wrapper, value) {
    wrapper.find('[data-test="MessageFormat"]').find("Select").first().prop("onChange")(value);
  }

  async function uploadFile(wrapper, name, content) {
    const file = new File([content], name, { type: "text/plain" });
    wrapper.find('input[data-test="SchemaFiles"]').simulate("change", { target: { files: [file] } });
    await settle(wrapper, 6);
  }

  test("automatic is the default and says what it covers", async () => {
    const wrapper = await analysed({});

    expect(wrapper.find('[data-test="ValueFormatMeaning"]').text()).toContain("schema registry");
    expect(wrapper.find('input[data-test="SchemaFiles"]').exists()).toBe(false);
  });

  test("protobuf asks for .proto files, checks them, and offers their messages", async () => {
    const wrapper = await analysed(
      {},
      Promise.resolve({ message_types: ["acme.Payment", "acme.Refund"], message_type: "acme.Payment" })
    );
    chooseFormat(wrapper, "protobuf");
    await settle(wrapper, 1);

    expect(wrapper.find('input[data-test="SchemaFiles"]').prop("accept")).toBe(".proto");
    expect(wrapper.find('button[data-test="EnableTopic"]').prop("disabled")).toBe(true);

    await uploadFile(wrapper, "payment.proto", PROTO);

    const checking = axios.post.mock.calls.find(([url]) => url.endsWith("/stream_schema"));
    expect(checking[1]).toEqual({
      value_format: "protobuf",
      schema_files: [{ name: "payment.proto", content: PROTO }],
    });
    expect(wrapper.find('[data-test="SchemaFileNames"]').text()).toBe("payment.proto");
    expect(wrapper.find('[data-test="MessageFormat"]').text()).toContain("Message type");
    expect(wrapper.find('button[data-test="EnableTopic"]').prop("disabled")).toBe(false);

    wrapper.find('button[data-test="EnableTopic"]').simulate("click");
    await settle(wrapper, 1);
    const enabling = axios.post.mock.calls.find(([url]) => url.endsWith("/topics/payments"));
    expect(enabling[1]).toMatchObject({
      value_format: "protobuf",
      message_type: "acme.Payment",
      schema_files: [{ name: "payment.proto", content: PROTO }],
    });
    expect(enabling[1].ready).toBeUndefined();
  });

  test("a schema that does not load is said under the upload, and nothing can be enabled with it", async () => {
    // Shaped as axios rejects: its own message is generic, and the reason is
    // in the response body.
    const refused = Object.assign(new Error("Request failed with status code 400"), {
      response: { status: 400, data: { message: "The .proto files do not compile: x.proto:2:1" } },
    });
    const wrapper = await analysed({}, Promise.reject(refused));
    chooseFormat(wrapper, "protobuf");
    await settle(wrapper, 1);

    await uploadFile(wrapper, "x.proto", "nope");

    expect(wrapper.find('[data-test="SchemaProblem"]').first().text()).toContain("x.proto:2:1");
    expect(wrapper.find('[data-test="SchemaProblem"]').first().text()).not.toContain("status code");
    expect(wrapper.find('button[data-test="EnableTopic"]').prop("disabled")).toBe(true);
  });

  test("an enabled avro topic shows its file and can be saved without uploading it again", async () => {
    const wrapper = await analysed({
      enabled: true,
      value_format: "avro",
      schema_files: ["order.avsc"],
      message_types: ["com.acme.Order"],
      message_type: "com.acme.Order",
    });

    expect(wrapper.find('[data-test="SchemaFileNames"]').text()).toBe("order.avsc");
    wrapper.find('button[data-test="SaveHowItReads"]').simulate("click");
    await settle(wrapper, 1);

    const saving = axios.post.mock.calls.find(([url]) => url.endsWith("/topics/payments"));
    expect(saving[1]).toMatchObject({ value_format: "avro", message_type: "com.acme.Order" });
    expect(saving[1].schema_files).toBeUndefined();
  });

  test("analysing again reads the topic the chosen way", async () => {
    const wrapper = await analysed({}, Promise.resolve({ message_types: ["Payment"], message_type: "Payment" }));
    chooseFormat(wrapper, "protobuf");
    await settle(wrapper, 1);
    await uploadFile(wrapper, "payment.proto", PROTO);

    wrapper.find('button[data-test="AnalyseAgain"]').simulate("click");
    await settle(wrapper);

    const again = axios.post.mock.calls.filter(([url]) => url.endsWith("/analyse")).pop();
    expect(again[1]).toMatchObject({ value_format: "protobuf", message_type: "Payment" });
  });

  test("what was found on the topic, and why nothing could be read, are said in words", async () => {
    const wrapper = await render([{ name: "payments", partitions: 1, enabled: false, columns: 0 }]);
    jest.spyOn(axios, "post").mockResolvedValue({
      ...analysis,
      formats: { Avro: 480, JSON: 20 },
      problem: null,
    });
    wrapper.find('[data-test="AnalyseTopic"]').first().simulate("click");
    await settle(wrapper);
    expect(wrapper.find('[data-test="FormatsFound"]').text()).toContain("Avro 480, JSON 20");

    axios.post.mockResolvedValue({
      ...analysis,
      columns: [],
      malformed: 500,
      problem: "Messages could not be read: no registry",
    });
    wrapper.find('button[data-test="AnalyseAgain"]').simulate("click");
    await settle(wrapper);
    expect(wrapper.find('[data-test="ReadingProblem"]').first().text()).toContain("no registry");
  });
});

describe("the rules for what a topic's messages are", () => {
  test("automatic sends nothing else", () => {
    expect(readingFormat("auto", [{ name: "x" }], "X")).toEqual({ value_format: "auto" });
  });

  test("files are sent only when they were uploaded here", () => {
    expect(readingFormat("avro", null, "com.acme.Order")).toEqual({
      value_format: "avro",
      message_type: "com.acme.Order",
    });
  });
});

describe("the rules for how a topic is read", () => {
  test("no name means nothing can be saved", () => {
    expect(readingSettings("", true, "latest").save_position).toBe(false);
  });

  test("and starting where it left off falls back to latest when nothing is saved", () => {
    expect(readingSettings("", true, "saved").start_from).toBe("latest");
    expect(readingSettings("g", false, "saved").start_from).toBe("latest");
  });

  test("with a name and saving, it may", () => {
    expect(readingSettings("g", true, "saved")).toEqual({
      consumer_group: "g",
      save_position: true,
      start_from: "saved",
    });
  });

  test("the name is trimmed, so a stray space is not a group of its own", () => {
    expect(readingSettings("  g  ", false, "latest").consumer_group).toBe("g");
  });
});
